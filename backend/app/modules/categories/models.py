from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "ix_categories_name_ru_trgm",
            text("lower(name_ru) gin_trgm_ops"),
            postgresql_using="gin",
        ),
        Index(
            "ix_categories_name_tk_trgm",
            text("lower(name_tk) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    name_ru: Mapped[str] = mapped_column(String(100))
    name_tk: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    icon: Mapped[str | None] = mapped_column(String(255))
    # Extra words to match in search, e.g. "женское пальто" for Женщинам › … › Пальто.
    search_aliases_ru: Mapped[str | None] = mapped_column(Text)
    search_aliases_tk: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
