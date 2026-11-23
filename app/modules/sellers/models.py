from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, str_enum
from app.enums import ModerationStatus


class SellerApplication(TimestampMixin, Base):
    __tablename__ = "seller_applications"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    shop_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="SET NULL")
    )
    shop_name: Mapped[str] = mapped_column(String(100))
    mall_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("malls.id", ondelete="SET NULL")
    )
    floor: Mapped[int | None] = mapped_column(Integer)
    row: Mapped[str | None] = mapped_column(String(16))
    number: Mapped[str | None] = mapped_column(String(16))
    city_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="SET NULL")
    )
    address: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str] = mapped_column(String(16))
    status: Mapped[ModerationStatus] = mapped_column(
        str_enum(ModerationStatus), default=ModerationStatus.pending, index=True
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
