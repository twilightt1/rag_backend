import uuid
from datetime import datetime
from sqlalchemy import String, Integer, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id:        Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title:          Mapped[str]       = mapped_column(String(500), server_default="New Conversation")
    document_count: Mapped[int]       = mapped_column(Integer(), server_default="0")
    created_at:     Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at:     Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    user:      Mapped["User"]           = relationship(back_populates="conversations")
    messages:  Mapped[list["Message"]]  = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    documents: Mapped[list["Document"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="Document.created_at")
