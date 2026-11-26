from pydantic import BaseModel

from app.modules.categories.schemas import CategoryBrief
from app.modules.malls.models import MallLayout
from app.modules.malls.schemas import MallListItem
from app.modules.shops.schemas import ShopBrief


class CategorySuggestion(CategoryBrief):
    path_ru: list[str]
    path_tk: list[str]
    shop_count: int


class MallCount(BaseModel):
    mall_id: int
    name_ru: str
    name_tk: str
    layout: MallLayout
    shop_count: int


class SuggestOut(BaseModel):
    categories: list[CategorySuggestion]
    malls_for_top_category: list[MallCount]
    shops: list[ShopBrief]


class SearchGroup(BaseModel):
    mall: MallListItem | None
    shop_count: int
    shops: list[ShopBrief]


class SearchOut(BaseModel):
    category: CategoryBrief | None
    total_shops: int
    total_malls: int
    groups: list[SearchGroup]
    similar_categories: list[CategoryBrief]
