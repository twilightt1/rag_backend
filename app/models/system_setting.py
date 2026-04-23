import uuid
from datetime import datetime
from sqlalchemy import String, TIMESTAMP, text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key:          Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    value:        Mapped[dict]      = mapped_column(JSON, nullable=False)
    description:  Mapped[str|None]  = mapped_column(String(500), nullable=True)
    created_at:   Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at:   Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)
