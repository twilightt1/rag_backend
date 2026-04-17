"""Authentication business logic."""
from __future__ import annotations
import logging, random, secrets, string
from datetime import datetime, timedelta, timezone
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.email_verification import EmailVerification
from app.models.password_reset_session import PasswordResetSession
from app.redis_client import get_redis
from app.utils.security import create_access_token

log     = logging.getLogger(__name__)
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
OTP_MAX = 5
_now    = lambda: datetime.now(timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _hash(pw: str) -> str:            return pwd_ctx.hash(pw)
def _verify(pw: str, h: str) -> bool: return pwd_ctx.verify(pw, h)
def _otp() -> str:                    return "".join(random.choices(string.digits, k=6))


# ── Register ──────────────────────────────────────────────────────────────────
async def register_email(db: AsyncSession, email: str, password: str) -> User:
    from fastapi import HTTPException
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        detail = ("Email already registered via Google. Please sign in with Google."
                  if existing.auth_provider == "google"
                  else "Email already in use.")
        raise HTTPException(409, detail=detail)

    user = User(email=email, hashed_password=_hash(password), auth_provider="email",
                is_verified=False, onboarding_done=False)
    db.add(user)
    await db.flush()

    otp, token = _otp(), secrets.token_urlsafe(64)
    db.add(EmailVerification(
        user_id=user.id, token=token, token_type="verify",
        otp_code=otp, otp_attempts=0,
        expires_at=_now() + timedelta(hours=24),
    ))
    # Create quota record
    from app.models.user_quota import UserQuota
    db.add(UserQuota(user_id=user.id))
    await db.commit()
    await db.refresh(user)

    from app.tasks.email_tasks import send_verification_email
    send_verification_email.delay(email, otp, token)
    return user


# ── OTP Verify ────────────────────────────────────────────────────────────────
async def verify_email_otp(db: AsyncSession, email: str, otp_code: str) -> User:
    from fastapi import HTTPException
    user = await db.scalar(select(User).where(User.email == email))
    if not user or user.is_verified:
        raise HTTPException(400, detail="Account not found or already verified.")

    ev = await db.scalar(
        select(EmailVerification).where(and_(
            EmailVerification.user_id == user.id,
            EmailVerification.token_type == "verify",
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > _now(),
        ))
    )
    if not ev:       raise HTTPException(400, detail="OTP expired. Please request a new one.")
    if ev.otp_attempts >= OTP_MAX:
        raise HTTPException(400, detail="Too many attempts. Please request a new code.")
    if ev.otp_code != otp_code:
        ev.otp_attempts += 1
        await db.commit()
        raise HTTPException(400, detail=f"Incorrect OTP. {OTP_MAX - ev.otp_attempts} attempts left.")

    user.is_verified = True
    ev.used_at = _now()
    await db.commit()
    await db.refresh(user)
    return user


# ── Link Verify ───────────────────────────────────────────────────────────────
async def verify_email_link(db: AsyncSession, token: str) -> User:
    from fastapi import HTTPException
    ev = await db.scalar(
        select(EmailVerification).where(and_(
            EmailVerification.token == token,
            EmailVerification.token_type == "verify",
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > _now(),
        ))
    )
    if not ev:
        raise HTTPException(400, detail="Invalid or expired verification link.")
    user = await db.get(User, ev.user_id)
    if not user:
        raise HTTPException(400, detail="Account not found.")
    user.is_verified = True
    ev.used_at = _now()
    await db.commit()
    await db.refresh(user)
    return user


# ── Resend ────────────────────────────────────────────────────────────────────
async def resend_verification(db: AsyncSession, email: str) -> None:
    from fastapi import HTTPException
    redis = await get_redis()
    key   = f"resend_limit:{email}"
    count = await redis.incr(key)
    if count == 1: await redis.expire(key, 3600)
    if count > 3:  raise HTTPException(429, detail="Too many resend requests. Try again in 1 hour.")

    user = await db.scalar(select(User).where(User.email == email))
    if not user or user.is_verified:
        return  # silent

    await db.execute(
        update(EmailVerification)
        .where(and_(EmailVerification.user_id == user.id,
                    EmailVerification.token_type == "verify",
                    EmailVerification.used_at.is_(None)))
        .values(used_at=_now())
    )
    otp, token = _otp(), secrets.token_urlsafe(64)
    db.add(EmailVerification(
        user_id=user.id, token=token, token_type="verify",
        otp_code=otp, otp_attempts=0,
        expires_at=_now() + timedelta(hours=24),
    ))
    await db.commit()
    from app.tasks.email_tasks import send_verification_email
    send_verification_email.delay(email, otp, token)


# ── Onboarding ────────────────────────────────────────────────────────────────
async def complete_onboarding(db: AsyncSession, user: User, display_name: str) -> tuple[User, str, str]:
    from fastapi import HTTPException
    if not user.is_verified:
        raise HTTPException(403, detail="Email not verified.")
    user.display_name    = display_name
    user.onboarding_done = True
    await db.commit()
    await db.refresh(user)
    access  = create_access_token({"sub": str(user.id), "role": user.role})
    refresh = await _create_refresh(user.id)
    return user, access, refresh


# ── Login ─────────────────────────────────────────────────────────────────────
async def login_email(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    from fastapi import HTTPException
    user = await db.scalar(select(User).where(User.email == email))
    if (not user or user.auth_provider != "email"
            or not user.hashed_password
            or not _verify(password, user.hashed_password)):
        raise HTTPException(401, detail="Invalid email or password.")
    if not user.is_verified:
        raise HTTPException(403, detail="Please verify your email first.")
    if not user.is_active:
        raise HTTPException(403, detail="Account deactivated.")
    access  = create_access_token({"sub": str(user.id), "role": user.role})
    refresh = await _create_refresh(user.id)
    return user, access, refresh


# ── Google OAuth ──────────────────────────────────────────────────────────────
async def find_or_create_google_user(db: AsyncSession, info: dict) -> User:
    from fastapi import HTTPException
    sub, email, picture = info["sub"], info["email"], info.get("picture")

    # Already linked Google account
    user = await db.scalar(select(User).where(User.google_id == sub))
    if user:
        if picture and user.avatar_url != picture:
            user.avatar_url = picture
            await db.commit()
        return user

    # Email already exists with password auth
    existing = await db.scalar(select(User).where(User.email == email))
    if existing:
        if existing.auth_provider == "email":
            raise HTTPException(409, detail="This email is registered with a password. Please log in with email.")
        existing.google_id  = sub
        existing.avatar_url = picture
        await db.commit()
        return existing

    # New Google user
    from app.models.user_quota import UserQuota
    user = User(
        email=email, auth_provider="google", google_id=sub,
        avatar_url=picture, is_verified=True, is_active=True,
        onboarding_done=False, display_name=None,
    )
    db.add(user)
    await db.flush()
    db.add(UserQuota(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    log.info("Google user created", extra={"user_id": str(user.id)})
    return user


# ── Forgot Password ───────────────────────────────────────────────────────────
async def create_password_reset_session(db: AsyncSession, email: str) -> None:
    from fastapi import HTTPException
    redis = await get_redis()
    key   = f"forgot_pw:{email}"
    count = await redis.incr(key)
    if count == 1: await redis.expire(key, 3600)
    if count > 3:  raise HTTPException(429, detail="Too many requests. Try again in 1 hour.")

    user = await db.scalar(
        select(User).where(and_(User.email == email, User.auth_provider == "email"))
    )
    if not user or not user.is_active:
        return  # silent — prevent email enumeration

    await db.execute(
        update(PasswordResetSession)
        .where(and_(PasswordResetSession.user_id == user.id,
                    PasswordResetSession.used_at.is_(None)))
        .values(used_at=_now())
    )
    otp, token = _otp(), secrets.token_urlsafe(64)
    db.add(PasswordResetSession(
        user_id=user.id, token=token, otp_code=otp,
        verified=False, expires_at=_now() + timedelta(minutes=15),
    ))
    await db.commit()
    from app.tasks.email_tasks import send_password_reset_email
    send_password_reset_email.delay(email, otp, token)


async def verify_reset_otp(db: AsyncSession, email: str, otp_code: str) -> str:
    from fastapi import HTTPException
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(400, detail="Invalid OTP or expired session.")

    session = await db.scalar(
        select(PasswordResetSession)
        .where(and_(
            PasswordResetSession.user_id == user.id,
            PasswordResetSession.verified == False,
            PasswordResetSession.used_at.is_(None),
            PasswordResetSession.expires_at > _now(),
        ))
        .order_by(PasswordResetSession.created_at.desc())
    )
    if not session:
        raise HTTPException(400, detail="Reset session expired. Please start over.")
    if session.otp_attempts >= OTP_MAX:
        raise HTTPException(400, detail="Too many attempts. Request a new code.")
    if session.otp_code != otp_code:
        session.otp_attempts += 1
        await db.commit()
        raise HTTPException(400, detail=f"Incorrect OTP. {OTP_MAX - session.otp_attempts} attempts left.")

    session.verified = True
    await db.commit()
    return session.token


async def verify_reset_link(db: AsyncSession, token: str) -> str:
    from fastapi import HTTPException
    session = await db.scalar(
        select(PasswordResetSession).where(and_(
            PasswordResetSession.token == token,
            PasswordResetSession.verified == False,
            PasswordResetSession.used_at.is_(None),
            PasswordResetSession.expires_at > _now(),
        ))
    )
    if not session:
        raise HTTPException(400, detail="Invalid or expired reset link.")
    session.verified = True
    await db.commit()
    return token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    from fastapi import HTTPException
    session = await db.scalar(
        select(PasswordResetSession).where(and_(
            PasswordResetSession.token == token,
            PasswordResetSession.verified == True,
            PasswordResetSession.used_at.is_(None),
            PasswordResetSession.expires_at > _now(),
        ))
    )
    if not session:
        raise HTTPException(400, detail="Invalid or expired reset session.")
    user = await db.get(User, session.user_id)
    if not user:
        raise HTTPException(400, detail="Account not found.")
    user.hashed_password = _hash(new_password)
    session.used_at = _now()
    await db.commit()
    await _invalidate_all_refresh(user.id)
    log.info("Password reset", extra={"user_id": str(user.id)})


# ── Profile ───────────────────────────────────────────────────────────────────
async def update_display_name(db: AsyncSession, user: User, display_name: str) -> User:
    user.display_name = display_name
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(db: AsyncSession, user: User, current: str, new_pw: str) -> None:
    from fastapi import HTTPException
    if user.auth_provider != "email":
        raise HTTPException(400, detail="Google accounts do not use passwords.")
    if not user.hashed_password or not _verify(current, user.hashed_password):
        raise HTTPException(400, detail="Current password is incorrect.")
    user.hashed_password = _hash(new_pw)
    await db.commit()
    await _invalidate_all_refresh(user.id)
    log.info("Password changed", extra={"user_id": str(user.id)})


# ── Token helpers ─────────────────────────────────────────────────────────────
async def _create_refresh(user_id: UUID | str) -> str:
    redis = await get_redis()
    token = secrets.token_urlsafe(64)
    ttl   = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis.setex(f"refresh:{token}", ttl, str(user_id))
    return token


async def _invalidate_all_refresh(user_id: UUID | str) -> None:
    redis  = await get_redis()
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="refresh:*", count=100)
        for key in keys:
            val = await redis.get(key)
            if val and val == str(user_id):
                await redis.delete(key)
        if cursor == 0:
            break
