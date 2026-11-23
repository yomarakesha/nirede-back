from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, str_enum
from app.enums import ModerationStatus


class Promotion(TimestampMixin, Base):
    __tablename__ = "promotions"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_promotion_period"),)

    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    title_ru: Mapped[str] = mapped_column(String(200))
    title_tk: Mapped[str] = mapped_column(String(200))
    badge: Mapped[str] = mapped_column(String(16))
    description_ru: Mapped[str | None] = mapped_column(Text)
    description_tk: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[ModerationStatus] = mapped_column(
        str_enum(ModerationStatus), default=ModerationStatus.pending, index=True
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)


def active_clause(now: datetime):
    return (
        (Promotion.status == ModerationStatus.approved)
        & (Promotion.starts_at <= now)
        & (Promotion.ends_at > now)
    )
