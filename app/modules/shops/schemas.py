from datetime import time

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.common import PatchModel, PhotoOut
from app.modules.categories.schemas import CategoryBrief
from app.modules.malls.schemas import MallRef
from app.storage import media_url

BRIEF_CATEGORIES = 3


class ShopFields(PatchModel):
    """Editable shop fields, all optional; shared by admin update and seller change requests."""

    model_config = ConfigDict(extra="forbid")
    non_nullable = frozenset({"name", "category_ids", "photos"})

    name: str | None = Field(default=None, min_length=1, max_length=100)
    logo: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    opens_at: time | None = None
    closes_at: time | None = None
    how_to_find_ru: str | None = None
    how_to_find_tk: str | None = None
    category_ids: list[int] | None = None
    photos: list[str] | None = None


class ShopLocationFields(BaseModel):
    mall_id: int | None = None
    city_id: int | None = None
    floor: int | None = Field(default=None, ge=0, le=500)
    row: str | None = Field(default=None, max_length=16)
    number: str | None = Field(default=None, max_length=16)
    address_ru: str | None = Field(default=None, max_length=255)
    address_tk: str | None = Field(default=None, max_length=255)


class ShopUpdate(ShopFields, ShopLocationFields):
    non_nullable = ShopFields.non_nullable | {"is_active"}

    is_active: bool | None = None


class ShopCreate(ShopUpdate):
    name: str = Field(min_length=1, max_length=100)
    category_ids: list[int] = []
    photos: list[str] = []
    is_active: bool = True


class ShopBrief(BaseModel):
    id: int
    name: str
    logo: str | None
    mall: MallRef | None
    city_id: int
    floor: int | None
    row: str | None
    number: str | None
    address_ru: str | None
    address_tk: str | None
    is_premium: bool
    categories: list[CategoryBrief]

    @computed_field
    @property
    def logo_url(self) -> str | None:
        return media_url(self.logo)


class ShopDetail(ShopBrief):
    phone: str | None
    opens_at: time | None
    closes_at: time | None
    how_to_find_ru: str | None
    how_to_find_tk: str | None
    photos: list[PhotoOut]
    is_open_now: bool
    is_saved: bool = False


class ShopAdminOut(ShopDetail):
    is_active: bool
    owner_id: int | None


class MallShopsOut(BaseModel):
    total: int
    items: list[ShopBrief]
