from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    exists,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin
from app.modules.categories.models import Category

shop_categories = Table(
    "shop_categories",
    Base.metadata,
    Column("shop_id", BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "category_id",
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)


class Shop(TimestampMixin, Base):
    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint(
            "(mall_id IS NOT NULL AND number IS NOT NULL"
            " AND address_ru IS NULL AND address_tk IS NULL)"
            " OR (mall_id IS NULL AND address_ru IS NOT NULL"
            " AND floor IS NULL AND row IS NULL AND number IS NULL)",
            name="ck_shop_location",
        ),
        Index("ix_shops_name_trgm", text("lower(name) gin_trgm_ops"), postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(String(100))
    logo: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    opens_at: Mapped[time | None] = mapped_column(Time)
    closes_at: Mapped[time | None] = mapped_column(Time)
    how_to_find_ru: Mapped[str | None] = mapped_column(Text)
    how_to_find_tk: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    city_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="RESTRICT"), index=True
    )
    mall_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("malls.id", ondelete="RESTRICT"), index=True
    )
    floor: Mapped[int | None] = mapped_column(Integer)
    row: Mapped[str | None] = mapped_column(String(16))
    number: Mapped[str | None] = mapped_column(String(16))
    address_ru: Mapped[str | None] = mapped_column(String(255))
    address_tk: Mapped[str | None] = mapped_column(String(255))
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    photos: Mapped[list["ShopPhoto"]] = relationship(
        order_by="ShopPhoto.position", cascade="all, delete-orphan", lazy="raise"
    )
    categories: Mapped[list[Category]] = relationship(secondary=shop_categories, lazy="raise")


class ShopPhoto(TimestampMixin, Base):
    __tablename__ = "shop_photos"

    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    activated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)


def premium_clause(now: datetime):
    """SQL boolean: the shop has a subscription active at `now`."""
    return exists(
        select(Subscription.id).where(
            Subscription.shop_id == Shop.id,
            Subscription.starts_at <= now,
            Subscription.ends_at > now,
        )
    )
