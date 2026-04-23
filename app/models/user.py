import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, TIMESTAMP, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email:           Mapped[str]       = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str|None]  = mapped_column(String(255), nullable=True)
    display_name:    Mapped[str|None]  = mapped_column(String(100), nullable=True)
    auth_provider:   Mapped[str]       = mapped_column(String(20), server_default="email")
    google_id:       Mapped[str|None]  = mapped_column(String(128), unique=True, nullable=True, index=True)
    avatar_url:      Mapped[str|None]  = mapped_column(String(500), nullable=True)
    onboarding_done: Mapped[bool]      = mapped_column(Boolean(), server_default="false")
    role:            Mapped[str]       = mapped_column(String(20), server_default="user")
    is_verified:     Mapped[bool]      = mapped_column(Boolean(), server_default="false")
    is_active:       Mapped[bool]      = mapped_column(Boolean(), server_default="true")
    is_deleted:      Mapped[bool]      = mapped_column(Boolean(), server_default="false")
    created_at:      Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at:      Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    email_verifications:     Mapped[list["EmailVerification"]]     = relationship(back_populates="user", cascade="all, delete-orphan")
    password_reset_sessions: Mapped[list["PasswordResetSession"]]  = relationship(back_populates="user", cascade="all, delete-orphan")
    conversations:           Mapped[list["Conversation"]]          = relationship(back_populates="user", cascade="all, delete-orphan")
    quota:                   Mapped["UserQuota"]                   = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
