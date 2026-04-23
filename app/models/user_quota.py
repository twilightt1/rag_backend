import uuid
from datetime import datetime, date
from sqlalchemy import Integer, Date, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class UserQuota(Base):
    __tablename__ = "user_quotas"

    id:                 Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id:            Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    requests_today:     Mapped[int]       = mapped_column(Integer(), server_default="0")
    requests_month:     Mapped[int]       = mapped_column(Integer(), server_default="0")
    tokens_today:       Mapped[int]       = mapped_column(Integer(), server_default="0")
    tokens_month:       Mapped[int]       = mapped_column(Integer(), server_default="0")
    daily_limit:        Mapped[int]       = mapped_column(Integer(), server_default="100")
    monthly_limit:      Mapped[int]       = mapped_column(Integer(), server_default="2000")
    last_daily_reset:   Mapped[date]      = mapped_column(Date(), server_default=text("CURRENT_DATE"))
    last_monthly_reset: Mapped[date]      = mapped_column(Date(), server_default=text("DATE_TRUNC('month', CURRENT_DATE)"))
    updated_at:         Mapped[datetime]  = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="quota")
