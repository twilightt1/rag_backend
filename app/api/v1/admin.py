"""Admin endpoints."""
from __future__ import annotations
from uuid import UUID
from datetime import datetime
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
from app.models.conversation import Conversation
from app.schemas.auth import UserResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin", tags=["admin"])


class UserUpdate(BaseModel):
    role:          str | None = None
    is_active:     bool | None = None
    is_deleted:    bool | None = None
    daily_limit:   int | None = None
    monthly_limit: int | None = None


class StatsResponse(BaseModel):
    total_users:          int
    active_users:         int
    total_documents:      int
    total_messages:       int
    pending_documents:    int

class UserActivitySummary(BaseModel):
    user_id:             UUID
    total_conversations: int
    total_messages:      int
    total_documents:     int
    last_message_at:     datetime | None
    last_document_at:    datetime | None


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    include_deleted: bool = False,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    if not include_deleted:
        query = query.where(User.is_deleted == False)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/activity", response_model=UserActivitySummary)
async def get_user_activity(
    user_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")

    total_convs = await db.scalar(select(func.count(Conversation.id)).where(Conversation.user_id == user_id))
    total_msgs = await db.scalar(select(func.count(Message.id)).where(Message.user_id == user_id))
    total_docs = await db.scalar(select(func.count(Document.id)).where(Document.user_id == user_id))

    last_msg = await db.scalar(select(func.max(Message.created_at)).where(Message.user_id == user_id))
    last_doc = await db.scalar(select(func.max(Document.created_at)).where(Document.user_id == user_id))

    return UserActivitySummary(
        user_id=user_id,
        total_conversations=total_convs or 0,
        total_messages=total_msgs or 0,
        total_documents=total_docs or 0,
        last_message_at=last_msg,
        last_document_at=last_doc
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, detail="User not found.")

    changes = {}

    if body.role is not None and user.role != body.role:
        changes["role"] = {"old": user.role, "new": body.role}
        user.role = body.role

    if body.is_active is not None and user.is_active != body.is_active:
        changes["is_active"] = {"old": user.is_active, "new": body.is_active}
        user.is_active = body.is_active

    if body.is_deleted is not None and user.is_deleted != body.is_deleted:
        changes["is_deleted"] = {"old": user.is_deleted, "new": body.is_deleted}
        user.is_deleted = body.is_deleted

    if body.daily_limit is not None or body.monthly_limit is not None:
        quota = await db.scalar(select(UserQuota).where(UserQuota.user_id == user_id))
        if quota:
            if body.daily_limit is not None and quota.daily_limit != body.daily_limit:
                changes["daily_limit"] = {"old": quota.daily_limit, "new": body.daily_limit}
                quota.daily_limit = body.daily_limit
            if body.monthly_limit is not None and quota.monthly_limit != body.monthly_limit:
                changes["monthly_limit"] = {"old": quota.monthly_limit, "new": body.monthly_limit}
                quota.monthly_limit = body.monthly_limit

    if changes:
        await AuditService.log_action(
            db=db,
            admin_id=admin_user.id,
            action="update_user",
            target_entity_type="user",
            target_entity_id=user_id,
            changes=changes
        )

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-quota", status_code=200)
async def reset_quota(
    user_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    quota = await db.scalar(select(UserQuota).where(UserQuota.user_id == user_id))
    if not quota:
        raise HTTPException(404, detail="Quota record not found.")

    changes = {
        "requests_today": {"old": quota.requests_today, "new": 0},
        "requests_month": {"old": quota.requests_month, "new": 0},
        "tokens_today": {"old": quota.tokens_today, "new": 0},
        "tokens_month": {"old": quota.tokens_month, "new": 0},
    }

    quota.requests_today = 0
    quota.requests_month = 0
    quota.tokens_today   = 0
    quota.tokens_month   = 0

    await AuditService.log_action(
        db=db,
        admin_id=admin_user.id,
        action="reset_quota",
        target_entity_type="user",
        target_entity_id=user_id,
        changes=changes
    )

    await db.commit()
    return {"message": "Quota reset successfully."}


class DocumentSummary(BaseModel):
    id:              UUID
    user_id:         UUID
    filename:        str
    file_size:       int | None
    mime_type:       str | None
    status:          str
    chunk_count:     int
    error_msg:       str | None
    created_at:      datetime
    updated_at:      datetime


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
    user_id: UUID | None = None,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(
        Document.id,
        Document.filename,
        Document.file_size,
        Document.mime_type,
        Document.status,
        Document.chunk_count,
        Document.error_msg,
        Document.created_at,
        Document.updated_at,
        Conversation.user_id
    ).join(Conversation).order_by(Document.created_at.desc()).offset(skip).limit(limit)

    if status:
        query = query.where(Document.status == status)
    if user_id:
        query = query.where(Conversation.user_id == user_id)

    result = await db.execute(query)

    docs = []
    for row in result.all():
        docs.append(DocumentSummary(
            id=row.id,
            user_id=row.user_id,
            filename=row.filename,
            file_size=row.file_size,
            mime_type=row.mime_type,
            status=row.status,
            chunk_count=row.chunk_count,
            error_msg=row.error_msg,
            created_at=row.created_at,
            updated_at=row.updated_at
        ))
    return docs


@router.post("/documents/{document_id}/retry", status_code=200)
async def retry_document(
    document_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, detail="Document not found.")

    if doc.status not in ["failed", "error"]:
        raise HTTPException(400, detail="Only failed documents can be retried.")

    changes = {
        "status": {"old": doc.status, "new": "pending"},
        "error_msg": {"old": doc.error_msg, "new": None}
    }

    doc.status = "pending"
    doc.error_msg = None

    await AuditService.log_action(
        db=db,
        admin_id=admin_user.id,
        action="retry_document",
        target_entity_type="document",
        target_entity_id=document_id,
        changes=changes
    )

    await db.commit()
                                                                                    
    return {"message": "Document marked for retry."}


@router.delete("/documents/{document_id}", status_code=200)
async def delete_document(
    document_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, detail="Document not found.")

                                                                       
                                                                           

    changes = {
        "status": {"old": doc.status, "new": "deleted"}
    }

                                                
    filename = doc.filename

    await AuditService.log_action(
        db=db,
        admin_id=admin_user.id,
        action="delete_document",
        target_entity_type="document",
        target_entity_id=document_id,
        changes={"filename": filename}
    )

    await db.delete(doc)
    await db.commit()
    return {"message": "Document deleted successfully."}


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
