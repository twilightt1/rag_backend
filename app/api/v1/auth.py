"""Auth endpoints — register, verify, login, Google OAuth, forgot password."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis_client import get_redis
from app.middleware.rate_limiter import check_rate_limit
from app.utils.dependencies import get_current_user, get_current_verified_user, bearer
from app.utils.security import create_access_token, decode_access_token
from app.services import auth_service
from app.services.oauth_service import google_oauth
from app.schemas.auth import (
    RegisterRequest, RegisterResponse,
    OTPVerifyRequest, OTPVerifyResponse,
    ResendVerificationRequest,
    OnboardingRequest, OnboardingResponse,
    LoginRequest, LoginResponse,
    ForgotPasswordRequest, ForgotPasswordResponse,
    ForgotPasswordOTPVerifyRequest, ForgotPasswordOTPVerifyResponse,
    ResetPasswordRequest, ResetPasswordResponse,
    UserResponse,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
log    = logging.getLogger(__name__)


# ── Register ──────────────────────────────────────────────────────────────────
@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    # Rate limit: 5 registrations per minute per IP
    await check_rate_limit(f"ip:{request.client.host}", window_seconds=60, limit=5)
    await auth_service.register_email(db, body.email, body.password)
    return RegisterResponse(message="Registration successful. Check your email for a verification code.")


# ── Email Verification — OTP ──────────────────────────────────────────────────
@router.post("/verify-email/otp", response_model=OTPVerifyResponse)
async def verify_email_otp(body: OTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    user  = await auth_service.verify_email_otp(db, body.email, body.otp_code)
    token = create_access_token(
        {"sub": str(user.id), "role": user.role, "scope": "onboarding"},
        expire_minutes=30,
    )
    return OTPVerifyResponse(message="Email verified.", access_token=token)


# ── Email Verification — Link ─────────────────────────────────────────────────
@router.get("/verify-email/link")
async def verify_email_link(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.verify_email_link(db, token)
    except HTTPException:
        return RedirectResponse(f"{settings.FRONTEND_URL}/verify-email?error=invalid_token")

    access = create_access_token(
        {"sub": str(user.id), "role": user.role, "scope": "onboarding"},
        expire_minutes=30,
    )
    return RedirectResponse(f"{settings.FRONTEND_URL}/onboarding?token={access}")


# ── Resend Verification ───────────────────────────────────────────────────────
@router.post("/verify-email/resend", status_code=200)
async def resend_verification(body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.resend_verification(db, body.email)
    return {"message": "If the account exists and is unverified, a new code has been sent."}


# ── Onboarding ────────────────────────────────────────────────────────────────
@router.post("/onboarding", response_model=OnboardingResponse)
async def onboarding(
    body: OnboardingRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user, access, refresh = await auth_service.complete_onboarding(db, current_user, body.display_name)
    return OnboardingResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    # Rate limit: 10 login attempts per minute per IP
    await check_rate_limit(f"ip:{request.client.host}", window_seconds=60, limit=10)
    user, access, refresh = await auth_service.login_email(db, body.email, body.password)
    return LoginResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


# ── Google OAuth ──────────────────────────────────────────────────────────────
@router.get("/google/authorize")
async def google_authorize():
    redis = await get_redis()
    url, state = google_oauth.create_authorization_url()
    await redis.setex(f"oauth_state:{state}", 300, "1")
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code:  str       = Query(...),
    state: str       = Query(...),
    error: str|None  = Query(None),
    db:    AsyncSession = Depends(get_db),
):
    if error:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_cancelled")

    redis  = await get_redis()
    cached = await redis.get(f"oauth_state:{state}")
    if not cached:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=invalid_state")
    await redis.delete(f"oauth_state:{state}")

    try:
        info = await google_oauth.exchange_code(code)
    except Exception as e:
        log.error("Google exchange failed", extra={"error": str(e)})
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_failed")

    try:
        user = await auth_service.find_or_create_google_user(db, info)
    except HTTPException as e:
        if e.status_code == 409:
            return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=email_already_registered")
        raise

    expire_min = 30 if not user.onboarding_done else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    scope      = "onboarding" if not user.onboarding_done else "full"
    access     = create_access_token({"sub": str(user.id), "role": user.role, "scope": scope},
                                      expire_minutes=expire_min)
    refresh    = await auth_service._create_refresh(user.id)
    dest       = "/onboarding" if not user.onboarding_done else "/chat"
    return RedirectResponse(f"{settings.FRONTEND_URL}{dest}?token={access}&refresh={refresh}")


# ── Token Refresh ─────────────────────────────────────────────────────────────
@router.post("/refresh")
async def refresh_token(refresh_token: str):
    redis     = await get_redis()
    user_id_b = await redis.get(f"refresh:{refresh_token}")
    if not user_id_b:
        raise HTTPException(401, detail="Refresh token invalid or expired.")

    user_id = user_id_b
    await redis.delete(f"refresh:{refresh_token}")

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == user_id))

    if not user or not user.is_active:
        raise HTTPException(401, detail="Account not found.")

    new_access  = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh = await auth_service._create_refresh(user.id)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    refresh_token: str|None = None,
    current_user=Depends(get_current_user),
):
    redis = await get_redis()
    if refresh_token:
        await redis.delete(f"refresh:{refresh_token}")

    # Blacklist the current access token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti")
            if jti:
                # Add to blacklist with TTL matching standard expiration
                # Using 1 hour (3600s) to be safe since ACCESS_TOKEN_EXPIRE_MINUTES is usually 15-30m
                exp_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 if hasattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES') else 3600
                await redis.setex(f"blacklist:{jti}", exp_seconds, "1")
        except Exception as e:
            log.warning(f"Failed to blacklist access token during logout: {e}")

    return {"message": "Logged out successfully."}


# ── Forgot Password ───────────────────────────────────────────────────────────
@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.create_password_reset_session(db, body.email)
    return ForgotPasswordResponse(
        message="If the account exists, you will receive password reset instructions."
    )


@router.post("/forgot-password/verify-otp", response_model=ForgotPasswordOTPVerifyResponse)
async def forgot_password_verify_otp(
    body: ForgotPasswordOTPVerifyRequest,
    db:   AsyncSession = Depends(get_db),
):
    reset_token = await auth_service.verify_reset_otp(db, body.email, body.otp_code)
    return ForgotPasswordOTPVerifyResponse(
        reset_token=reset_token,
        message="OTP verified. Please set your new password.",
    )


@router.get("/forgot-password/verify-link")
async def forgot_password_verify_link(
    token: str = Query(...),
    db:    AsyncSession = Depends(get_db),
):
    try:
        reset_token = await auth_service.verify_reset_link(db, token)
    except HTTPException:
        return RedirectResponse(f"{settings.FRONTEND_URL}/forgot-password?error=invalid_token")
    return RedirectResponse(f"{settings.FRONTEND_URL}/reset-password?token={reset_token}")


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(db, body.token, body.new_password)
    return ResetPasswordResponse(message="Password reset successfully. Please log in.")
