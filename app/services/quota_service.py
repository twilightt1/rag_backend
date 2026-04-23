"""User quota enforcement."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_quota import UserQuota


async def check_and_increment(user_id: UUID, db: AsyncSession) -> None:
    quota = await db.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(UserQuota)
        .where(UserQuota.user_id == user_id)
    )
    if not quota:
        return                           

    if quota.requests_today >= quota.daily_limit:
        raise HTTPException(429, detail="Daily quota exceeded.")
    if quota.requests_month >= quota.monthly_limit:
        raise HTTPException(429, detail="Monthly quota exceeded.")

    quota.requests_today  += 1
    quota.requests_month  += 1
    await db.commit()
