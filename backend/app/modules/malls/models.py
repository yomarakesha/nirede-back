from datetime import time
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, str_enum


class MallLayout(StrEnum):
    floors = "floors"
    rows = "rows"


class Mall(TimestampMixin, Base):
    __tablename__ = "malls"

    city_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="RESTRICT"), index=True
    )
    name_ru: Mapped[str] = mapped_column(String(100))
    name_tk: Mapped[str] = mapped_column(String(100))
    address_ru: Mapped[str] = mapped_column(String(255))
    address_tk: Mapped[str] = mapped_column(String(255))
    description_ru: Mapped[str | None] = mapped_column(Text)
    description_tk: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    opens_at: Mapped[time | None] = mapped_column(Time)
    closes_at: Mapped[time | None] = mapped_column(Time)
    layout: Mapped[MallLayout] = mapped_column(str_enum(MallLayout), default=MallLayout.floors)
    floors_count: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    photos: Mapped[list["MallPhoto"]] = relationship(
        order_by="MallPhoto.position", cascade="all, delete-orphan", lazy="raise"
    )
    floors: Mapped[list["MallFloor"]] = relationship(
        order_by="MallFloor.number", cascade="all, delete-orphan", lazy="raise"
    )


class MallPhoto(TimestampMixin, Base):
    __tablename__ = "mall_photos"

    mall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("malls.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)


class MallFloor(TimestampMixin, Base):
    __tablename__ = "mall_floors"
    __table_args__ = (UniqueConstraint("mall_id", "number"),)

    mall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("malls.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    label_ru: Mapped[str | None] = mapped_column(String(100))
    label_tk: Mapped[str | None] = mapped_column(String(100))
    summary_ru: Mapped[str] = mapped_column(String(255))
    summary_tk: Mapped[str] = mapped_column(String(255))
