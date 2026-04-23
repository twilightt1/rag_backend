"""User profile endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.utils.dependencies import get_current_verified_user
from app.services import auth_service
from app.schemas.auth import UserResponse, UpdateProfileRequest, ChangePasswordRequest, ChangePasswordResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_verified_user)):
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user=Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.update_display_name(db, current_user, body.display_name)
    return UserResponse.model_validate(user)


@router.post("/me/change-password", response_model=ChangePasswordResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.change_password(db, current_user, body.current_password, body.new_password)
    return ChangePasswordResponse(message="Password changed. Please log in again.")
