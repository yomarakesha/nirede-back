from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.storage import media_url


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_ru: str
    name_tk: str
    slug: str
    icon: str | None = None

    @computed_field
    @property
    def icon_url(self) -> str | None:
        return media_url(self.icon)


class CategoryNode(CategoryBrief):
    children: list["CategoryNode"] = []


class CategoryAdminOut(CategoryBrief):
    parent_id: int | None
    search_aliases_ru: str | None
    search_aliases_tk: str | None
    sort_order: int
    is_active: bool


class CategoryCreate(BaseModel):
    parent_id: int | None = None
    name_ru: str = Field(min_length=1, max_length=100)
    name_tk: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    icon: str | None = None
    search_aliases_ru: str | None = None
    search_aliases_tk: str | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    parent_id: int | None = None
    name_ru: str | None = Field(default=None, min_length=1, max_length=100)
    name_tk: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    icon: str | None = None
    search_aliases_ru: str | None = None
    search_aliases_tk: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
