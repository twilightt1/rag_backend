import uuid
from datetime import datetime
from sqlalchemy import String, CHAR, SmallInteger, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id:           Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id:      Mapped[uuid.UUID]    = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token:        Mapped[str]          = mapped_column(String(128), unique=True, nullable=False, index=True)
    token_type:   Mapped[str]          = mapped_column(String(20), server_default="verify")
    otp_code:     Mapped[str|None]     = mapped_column(CHAR(6), nullable=True)
    otp_attempts: Mapped[int]          = mapped_column(SmallInteger(), server_default="0")
    expires_at:   Mapped[datetime]     = mapped_column(TIMESTAMP(timezone=True))
    used_at:      Mapped[datetime|None]= mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at:   Mapped[datetime]     = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))

    user: Mapped["User"] = relationship(back_populates="email_verifications")
