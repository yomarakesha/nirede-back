from datetime import time

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.common import PhotoOut
from app.modules.categories.schemas import CategoryBrief
from app.modules.malls.models import MallLayout
from app.storage import media_url


class MallBase(BaseModel):
    name_ru: str = Field(min_length=1, max_length=100)
    name_tk: str = Field(min_length=1, max_length=100)
    address_ru: str = Field(min_length=1, max_length=255)
    address_tk: str = Field(min_length=1, max_length=255)
    description_ru: str | None = None
    description_tk: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    opens_at: time | None = None
    closes_at: time | None = None
    layout: MallLayout = MallLayout.floors
    floors_count: int | None = Field(default=None, ge=1, le=50)
    is_active: bool = True
    sort_order: int = 0


class MallCreate(MallBase):
    city_id: int

    @model_validator(mode="after")
    def _floors_need_count(self) -> "MallCreate":
        if self.layout == MallLayout.floors and self.floors_count is None:
            raise ValueError("floors_count is required for layout 'floors'")
        return self


class MallUpdate(BaseModel):
    city_id: int | None = None
    name_ru: str | None = Field(default=None, min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, min_length=1, max_length=100)
    address_ru: str | None = Field(default=None, min_length=1, max_length=255)
    address_tk: str | None = Field(default=None, min_length=1, max_length=255)
    description_ru: str | None = None
    description_tk: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    opens_at: time | None = None
    closes_at: time | None = None
    layout: MallLayout | None = None
    floors_count: int | None = Field(default=None, ge=1, le=50)
    is_active: bool | None = None
    sort_order: int | None = None


class MallFloorIn(BaseModel):
    number: int = Field(ge=0, le=500)
    label_ru: str | None = Field(default=None, max_length=100)
    label_tk: str | None = Field(default=None, max_length=100)
    summary_ru: str = Field(max_length=255)
    summary_tk: str = Field(max_length=255)


class MallFloorOut(MallFloorIn):
    model_config = ConfigDict(from_attributes=True)


class MallRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_ru: str
    name_tk: str
    layout: MallLayout


class MallListItem(MallRef):
    address_ru: str
    address_tk: str
    floors_count: int | None
    opens_at: time | None
    closes_at: time | None
    description_ru: str | None
    description_tk: str | None
    cover: str | None = None

    @computed_field
    @property
    def cover_url(self) -> str | None:
        return media_url(self.cover)


class MallAdminOut(MallListItem):
    city_id: int
    phone: str | None
    is_active: bool
    sort_order: int


class MallDetail(MallListItem):
    city_id: int
    phone: str | None
    photos: list[PhotoOut]
    floors: list[MallFloorOut]
    is_open_now: bool
    shop_count: int = 0
    root_categories: list[CategoryBrief] = []
