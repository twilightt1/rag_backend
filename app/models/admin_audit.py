import uuid
from datetime import datetime
from sqlalchemy import String, TIMESTAMP, text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AdminActionLog(Base):
    __tablename__ = "admin_audit_logs"

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_id:           Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    target_entity_type: Mapped[str]       = mapped_column(String(50), nullable=False)
    target_entity_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action:             Mapped[str]       = mapped_column(String(50), nullable=False)
    changes:            Mapped[dict]      = mapped_column(JSON, nullable=True)
    created_at:         Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    admin: Mapped["User"] = relationship()
