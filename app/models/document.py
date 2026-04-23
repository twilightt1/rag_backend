import uuid
from datetime import datetime
from sqlalchemy import String, BigInteger, Integer, Text, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id:              Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    filename:        Mapped[str]          = mapped_column(String(500), nullable=False)
    file_path:       Mapped[str]          = mapped_column(String(1000), nullable=False)
    file_size:       Mapped[int|None]     = mapped_column(BigInteger, nullable=True)
    mime_type:       Mapped[str|None]     = mapped_column(String(100), nullable=True)
    status:          Mapped[str]          = mapped_column(String(20), server_default="pending")
    chunk_count:     Mapped[int]          = mapped_column(Integer(), server_default="0")
    error_msg:       Mapped[str|None]     = mapped_column(Text, nullable=True)
    created_at:      Mapped[datetime]     = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at:      Mapped[datetime]     = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    conversation: Mapped["Conversation"]        = relationship(back_populates="documents")
    chunks:       Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
