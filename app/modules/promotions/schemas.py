from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, model_validator

from app.common import PatchModel
from app.enums import ModerationStatus
from app.modules.shops.schemas import ShopBrief
from app.storage import media_url


class PromotionUpdate(PatchModel):
    model_config = ConfigDict(extra="forbid")
    non_nullable = frozenset({"title_ru", "title_tk", "badge", "starts_at", "ends_at"})

    title_ru: str | None = Field(default=None, min_length=1, max_length=200)
    title_tk: str | None = Field(default=None, min_length=1, max_length=200)
    badge: str | None = Field(default=None, min_length=1, max_length=16)
    description_ru: str | None = None
    description_tk: str | None = None
    image: str | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


class PromotionFields(PromotionUpdate):
    """Body of a new promotion without the shop (seller passes the shop in the URL)."""

    title_ru: str = Field(min_length=1, max_length=200)
    title_tk: str = Field(min_length=1, max_length=200)
    badge: str = Field(min_length=1, max_length=16)
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def _period(self) -> "PromotionFields":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class PromotionCreate(PromotionFields):
    shop_id: int


class ReviewIn(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class PromotionOut(BaseModel):
    id: int
    title_ru: str
    title_tk: str
    badge: str
    description_ru: str | None
    description_tk: str | None
    image: str | None
    starts_at: datetime
    ends_at: datetime
    status: ModerationStatus
    admin_comment: str | None
    shop: ShopBrief

    @computed_field
    @property
    def image_url(self) -> str | None:
        return media_url(self.image)


class PromotionsFeed(BaseModel):
    featured: PromotionOut | None
    items: list[PromotionOut]
