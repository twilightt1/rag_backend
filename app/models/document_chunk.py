import uuid
from datetime import datetime
from sqlalchemy import Text, Integer, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content:     Mapped[str]       = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int]       = mapped_column(Integer(), nullable=False)
    chunk_metadata: Mapped[dict]      = mapped_column(JSONB, server_default="{}")
    created_at:  Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    document: Mapped["Document"] = relationship(back_populates="chunks")
