from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, str_enum
from app.enums import ModerationStatus


class EntityType(StrEnum):
    shop = "shop"
    promotion = "promotion"


class ChangeRequest(TimestampMixin, Base):
    """A seller's pending edit of a live object; applied only when an admin approves it."""

    __tablename__ = "change_requests"
    __table_args__ = (
        Index(
            "uq_change_requests_one_pending",
            "entity_type",
            "entity_id",
            "author_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    entity_type: Mapped[EntityType] = mapped_column(str_enum(EntityType))
    entity_id: Mapped[int] = mapped_column(BigInteger, index=True)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[ModerationStatus] = mapped_column(
        str_enum(ModerationStatus), default=ModerationStatus.pending, index=True
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
