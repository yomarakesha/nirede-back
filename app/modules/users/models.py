from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, str_enum
from app.enums import Language, UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.user)
    language: Mapped[Language] = mapped_column(str_enum(Language), default=Language.ru)
    notify_favorite_shops: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_my_malls: Mapped[bool] = mapped_column(Boolean, default=True)


class OtpCode(TimestampMixin, Base):
    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
