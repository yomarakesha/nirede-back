from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class City(TimestampMixin, Base):
    __tablename__ = "cities"

    name_ru: Mapped[str] = mapped_column(String(100))
    name_tk: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
