"""Admin endpoints."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.dependencies import require_admin
from app.models.user import User
from app.models.user_quota import UserQuota
from app.models.document import Document
from app.models.message import Message
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


class UserUpdate(BaseModel):
    role:          str | None = None
    is_active:     bool | None = None
    daily_limit:   int | None = None
    monthly_limit: int | None = None


class StatsResponse(BaseModel):
    total_users:          int
    active_users:         int
    total_documents:      int
    total_messages:       int
    pending_documents:    int


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    if body.daily_limit is not None or body.monthly_limit is not None:
        quota = await db.scalar(select(UserQuota).where(UserQuota.user_id == user_id))
        if quota:
            if body.daily_limit is not None:
                quota.daily_limit = body.daily_limit
            if body.monthly_limit is not None:
                quota.monthly_limit = body.monthly_limit

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-quota", status_code=200)
async def reset_quota(
    user_id: UUID,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    quota = await db.scalar(select(UserQuota).where(UserQuota.user_id == user_id))
    if not quota:
        raise HTTPException(404, detail="Quota record not found.")
    quota.requests_today = 0
    quota.requests_month = 0
    quota.tokens_today   = 0
    quota.tokens_month   = 0
    await db.commit()
    return {"message": "Quota reset successfully."}


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users     = await db.scalar(select(func.count(User.id)))
    active_users    = await db.scalar(select(func.count(User.id)).where(User.is_active == True))
    total_docs      = await db.scalar(select(func.count(Document.id)))
    pending_docs    = await db.scalar(select(func.count(Document.id)).where(
                            Document.status.in_(["pending", "processing"])
                        ))
    total_messages  = await db.scalar(select(func.count(Message.id)))

    return StatsResponse(
        total_users=total_users or 0,
        active_users=active_users or 0,
        total_documents=total_docs or 0,
        total_messages=total_messages or 0,
        pending_documents=pending_docs or 0,
    )
