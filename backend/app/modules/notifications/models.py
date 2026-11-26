from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    promotion_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("promotions.id", ondelete="SET NULL")
    )
    title_ru: Mapped[str] = mapped_column(String(200))
    title_tk: Mapped[str] = mapped_column(String(200))
    body_ru: Mapped[str] = mapped_column(Text)
    body_tk: Mapped[str] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceToken(TimestampMixin, Base):
    __tablename__ = "device_tokens"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[str] = mapped_column(String(16))
