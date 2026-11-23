from collections import defaultdict
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import PhotoOut
from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryBrief
from app.modules.cities.models import City
from app.modules.cities.service import get_city_or_404
from app.modules.malls.models import Mall, MallLayout
from app.modules.malls.schemas import MallRef
from app.modules.shops.models import Shop, ShopPhoto, premium_clause, shop_categories
from app.modules.shops.schemas import (
    BRIEF_CATEGORIES,
    ShopAdminOut,
    ShopBrief,
    ShopCreate,
    ShopDetail,
    ShopUpdate,
)
from app.timeutil import is_open, utcnow

LOCATION_FIELDS = ("mall_id", "city_id", "floor", "row", "number", "address_ru", "address_tk")


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def public_shops() -> Select:
    """Active shops whose city (and mall, if any) are active."""
    return (
        select(Shop)
        .join(City, City.id == Shop.city_id)
        .outerjoin(Mall, Mall.id == Shop.mall_id)
        .where(Shop.is_active, City.is_active, or_(Shop.mall_id.is_(None), Mall.is_active))
    )


async def get_shop_or_404(session: AsyncSession, shop_id: int, *, public: bool) -> Shop:
    stmt = (public_shops() if public else select(Shop)).where(Shop.id == shop_id)
    shop = await session.scalar(stmt)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shop_not_found")
    return shop


async def _validate_location(session: AsyncSession, shop: Shop) -> None:
    """Check and normalise the location; fields that do not apply are cleared."""
    if shop.mall_id is not None:
        mall = await session.get(Mall, shop.mall_id)
        if mall is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "mall_not_found")
        shop.city_id = mall.city_id
        shop.address_ru = shop.address_tk = None
        if mall.layout == MallLayout.floors:
            if shop.floor is None:
                raise _invalid("floor_required")
            if not 1 <= shop.floor <= (mall.floors_count or 0):
                raise _invalid("floor_out_of_range")
            if shop.row is not None:
                raise _invalid("row_not_allowed")
        else:
            if not shop.row:
                raise _invalid("row_required")
            if shop.floor is not None:
                raise _invalid("floor_not_allowed")
        if not shop.number:
            raise _invalid("number_required")
    else:
        shop.floor = shop.row = shop.number = None
        if shop.city_id is None:
            raise _invalid("city_required")
        await get_city_or_404(session, shop.city_id)
        if not shop.address_ru:
            raise _invalid("address_required")


async def _set_categories(session: AsyncSession, shop: Shop, ids: list[int]) -> None:
    ids = list(dict.fromkeys(ids))
    if ids:
        found = set(await session.scalars(select(Category.id).where(Category.id.in_(ids))))
        if found != set(ids):
            raise _invalid("unknown_category")
    await session.execute(delete(shop_categories).where(shop_categories.c.shop_id == shop.id))
    if ids:
        await session.execute(
            insert(shop_categories), [{"shop_id": shop.id, "category_id": i} for i in ids]
        )


async def _set_photos(session: AsyncSession, shop: Shop, paths: list[str]) -> None:
    await session.execute(delete(ShopPhoto).where(ShopPhoto.shop_id == shop.id))
    session.add_all(ShopPhoto(shop_id=shop.id, path=p, position=i) for i, p in enumerate(paths))


async def _apply(session: AsyncSession, shop: Shop, values: dict[str, Any]) -> None:
    category_ids = values.pop("category_ids", None)
    photos = values.pop("photos", None)
    for field, value in values.items():
        setattr(shop, field, value)
    await _validate_location(session, shop)
    session.add(shop)
    await session.flush()
    if category_ids is not None:
        await _set_categories(session, shop, category_ids)
    if photos is not None:
        await _set_photos(session, shop, photos)


async def create_shop(session: AsyncSession, data: ShopCreate, *, commit: bool = True) -> Shop:
    shop = Shop()
    await _apply(session, shop, data.model_dump())
    if commit:
        await session.commit()
    return shop


async def update_shop(
    session: AsyncSession, shop: Shop, data: ShopUpdate, *, commit: bool = True
) -> Shop:
    await _apply(session, shop, data.model_dump(exclude_unset=True))
    if commit:
        await session.commit()
    return shop


async def _premium_ids(session: AsyncSession, shop_ids: list[int]) -> set[int]:
    if not shop_ids:
        return set()
    rows = await session.scalars(
        select(Shop.id).where(Shop.id.in_(shop_ids), premium_clause(utcnow()))
    )
    return set(rows)


async def _categories_by_shop(
    session: AsyncSession, shop_ids: list[int]
) -> dict[int, list[CategoryBrief]]:
    rows = await session.execute(
        select(shop_categories.c.shop_id, Category)
        .join(Category, Category.id == shop_categories.c.category_id)
        .where(shop_categories.c.shop_id.in_(shop_ids), Category.is_active)
        .order_by(Category.sort_order, Category.id)
    )
    result: dict[int, list[CategoryBrief]] = defaultdict(list)
    for shop_id, cat in rows:
        result[shop_id].append(CategoryBrief.model_validate(cat))
    return result


async def _malls_by_id(session: AsyncSession, mall_ids: set[int]) -> dict[int, MallRef]:
    if not mall_ids:
        return {}
    rows = await session.scalars(select(Mall).where(Mall.id.in_(mall_ids)))
    return {m.id: MallRef.model_validate(m) for m in rows}


def _brief_fields(shop: Shop, malls, premium, cats, *, all_categories: bool) -> dict:
    categories = cats.get(shop.id, [])
    return {
        "id": shop.id,
        "name": shop.name,
        "logo": shop.logo,
        "mall": malls.get(shop.mall_id) if shop.mall_id else None,
        "city_id": shop.city_id,
        "floor": shop.floor,
        "row": shop.row,
        "number": shop.number,
        "address_ru": shop.address_ru,
        "address_tk": shop.address_tk,
        "is_premium": shop.id in premium,
        "categories": categories if all_categories else categories[:BRIEF_CATEGORIES],
    }


async def load_briefs(session: AsyncSession, shops: list[Shop]) -> list[ShopBrief]:
    ids = [s.id for s in shops]
    premium = await _premium_ids(session, ids)
    cats = await _categories_by_shop(session, ids)
    malls = await _malls_by_id(session, {s.mall_id for s in shops if s.mall_id})
    return [
        ShopBrief(**_brief_fields(s, malls, premium, cats, all_categories=False)) for s in shops
    ]


async def load_detail(session: AsyncSession, shop: Shop, *, admin: bool = False) -> ShopDetail:
    premium = await _premium_ids(session, [shop.id])
    cats = await _categories_by_shop(session, [shop.id])
    malls = await _malls_by_id(session, {shop.mall_id} if shop.mall_id else set())
    photos = await session.scalars(
        select(ShopPhoto.path).where(ShopPhoto.shop_id == shop.id).order_by(ShopPhoto.position)
    )
    fields = {
        **_brief_fields(shop, malls, premium, cats, all_categories=True),
        "phone": shop.phone,
        "opens_at": shop.opens_at,
        "closes_at": shop.closes_at,
        "how_to_find_ru": shop.how_to_find_ru,
        "how_to_find_tk": shop.how_to_find_tk,
        "photos": [PhotoOut(path=p) for p in photos],
        "is_open_now": is_open(shop.opens_at, shop.closes_at, utcnow()),
    }
    if admin:
        return ShopAdminOut(**fields, is_active=shop.is_active, owner_id=shop.owner_id)
    return ShopDetail(**fields)


def order_premium_first(stmt: Select) -> Select:
    return stmt.order_by(premium_clause(utcnow()).desc(), Shop.name, Shop.id)
