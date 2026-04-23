import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role:            Mapped[str]       = mapped_column(String(20), nullable=False)
    content:         Mapped[str]       = mapped_column(Text, nullable=False)
    agent_trace:     Mapped[dict]      = mapped_column(JSONB, server_default="{}")
    token_count:     Mapped[int|None]  = mapped_column(Integer(), nullable=True)
    created_at:      Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
