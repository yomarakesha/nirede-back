from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.storage import media_url


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    promotion_id: int | None
    title_ru: str
    title_tk: str
    body_ru: str
    body_tk: str
    image: str | None
    read_at: datetime | None
    created_at: datetime

    @computed_field
    @property
    def image_url(self) -> str | None:
        return media_url(self.image)


class UnreadCount(BaseModel):
    count: int


class DeviceIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: Literal["ios", "android"]
