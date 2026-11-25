from collections import defaultdict
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, exists, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import PhotoOut
from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryBrief
from app.modules.cities.models import City
from app.modules.cities.service import get_city_or_404
from app.modules.malls.models import Mall, MallLayout
from app.modules.malls.schemas import MallRef
from app.modules.shops.models import (
    Shop,
    ShopLocation,
    ShopPhoto,
    premium_clause,
    shop_categories,
)
from app.modules.shops.schemas import (
    BRIEF_CATEGORIES,
    LocationIn,
    LocationOut,
    ShopAdminOut,
    ShopBrief,
    ShopCreate,
    ShopDetail,
    ShopUpdate,
)
from app.timeutil import is_open, utcnow


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _visible(stmt: Select) -> Select:
    """Keep locations whose city (and mall, if any) are active."""
    return (
        stmt.join(City, City.id == ShopLocation.city_id)
        .outerjoin(Mall, Mall.id == ShopLocation.mall_id)
        .where(City.is_active, or_(ShopLocation.mall_id.is_(None), Mall.is_active))
    )


def located(
    *,
    city_id: int | None = None,
    mall_id: int | None = None,
    floor: int | None = None,
    row: str | None = None,
    public: bool = True,
):
    """SQL boolean: the shop has a location matching the filters (a visible one if `public`)."""
    stmt = select(ShopLocation.id).where(ShopLocation.shop_id == Shop.id)
    if public:
        stmt = _visible(stmt)
    for column, value in (
        (ShopLocation.city_id, city_id),
        (ShopLocation.mall_id, mall_id),
        (ShopLocation.floor, floor),
        (ShopLocation.row, row),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return exists(stmt)


def public_shops() -> Select:
    """Active shops with at least one visible location."""
    return select(Shop).where(Shop.is_active, located())


async def get_shop_or_404(session: AsyncSession, shop_id: int, *, public: bool) -> Shop:
    stmt = (public_shops() if public else select(Shop)).where(Shop.id == shop_id)
    shop = await session.scalar(stmt)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shop_not_found")
    return shop


async def _to_location(session: AsyncSession, data: LocationIn, position: int) -> ShopLocation:
    """Check and normalise a location; fields that do not apply are cleared."""
    loc = ShopLocation(**data.model_dump(), position=position)
    if loc.mall_id is not None:
        mall = await session.get(Mall, loc.mall_id)
        if mall is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "mall_not_found")
        loc.city_id = mall.city_id
        loc.address_ru = loc.address_tk = None
        if mall.layout == MallLayout.floors:
            if loc.floor is None:
                raise _invalid("floor_required")
            if not 1 <= loc.floor <= (mall.floors_count or 0):
                raise _invalid("floor_out_of_range")
            if loc.row is not None:
                raise _invalid("row_not_allowed")
        else:
            if not loc.row:
                raise _invalid("row_required")
            if loc.floor is not None:
                raise _invalid("floor_not_allowed")
        if not loc.number:
            raise _invalid("number_required")
    else:
        loc.floor = loc.row = loc.number = None
        if loc.city_id is None:
            raise _invalid("city_required")
        await get_city_or_404(session, loc.city_id)
        if not loc.address_ru:
            raise _invalid("address_required")
    return loc


async def _set_locations(session: AsyncSession, shop: Shop, items: list[LocationIn]) -> None:
    locations = [await _to_location(session, item, i) for i, item in enumerate(items)]
    await session.execute(delete(ShopLocation).where(ShopLocation.shop_id == shop.id))
    for loc in locations:
        loc.shop_id = shop.id
    session.add_all(locations)


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
    locations = values.pop("locations", None)
    for field, value in values.items():
        setattr(shop, field, value)
    session.add(shop)
    await session.flush()
    if category_ids is not None:
        await _set_categories(session, shop, category_ids)
    if photos is not None:
        await _set_photos(session, shop, photos)
    if locations is not None:
        await _set_locations(session, shop, locations)


async def create_shop(session: AsyncSession, data: ShopCreate, *, commit: bool = True) -> Shop:
    shop = Shop()
    await _apply(session, shop, {**data.model_dump(), "locations": data.locations})
    if commit:
        await session.commit()
    return shop


async def update_shop(
    session: AsyncSession, shop: Shop, data: ShopUpdate, *, commit: bool = True
) -> Shop:
    values = data.model_dump(exclude_unset=True)
    if "locations" in values:
        values["locations"] = data.locations
    await _apply(session, shop, values)
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


async def _locations_by_shop(
    session: AsyncSession, shop_ids: list[int], *, public: bool
) -> dict[int, list[LocationOut]]:
    stmt = select(ShopLocation).where(ShopLocation.shop_id.in_(shop_ids))
    if public:
        stmt = _visible(stmt)
    locations = list(
        await session.scalars(stmt.order_by(ShopLocation.shop_id, ShopLocation.position))
    )
    mall_ids = {loc.mall_id for loc in locations if loc.mall_id}
    malls = {}
    if mall_ids:
        rows = await session.scalars(select(Mall).where(Mall.id.in_(mall_ids)))
        malls = {m.id: MallRef.model_validate(m) for m in rows}
    result: dict[int, list[LocationOut]] = defaultdict(list)
    for loc in locations:
        result[loc.shop_id].append(
            LocationOut(
                id=loc.id,
                city_id=loc.city_id,
                mall=malls.get(loc.mall_id) if loc.mall_id else None,
                floor=loc.floor,
                row=loc.row,
                number=loc.number,
                address_ru=loc.address_ru,
                address_tk=loc.address_tk,
            )
        )
    return result


def _brief_fields(shop: Shop, locations, premium, cats, *, all_categories: bool) -> dict:
    categories = cats.get(shop.id, [])
    return {
        "id": shop.id,
        "name": shop.name,
        "logo": shop.logo,
        "locations": locations.get(shop.id, []),
        "is_premium": shop.id in premium,
        "categories": categories if all_categories else categories[:BRIEF_CATEGORIES],
    }


async def load_briefs(
    session: AsyncSession, shops: list[Shop], *, public: bool = True
) -> list[ShopBrief]:
    """With `public`, only visible locations are listed."""
    ids = [s.id for s in shops]
    premium = await _premium_ids(session, ids)
    cats = await _categories_by_shop(session, ids)
    locations = await _locations_by_shop(session, ids, public=public)
    return [
        ShopBrief(**_brief_fields(s, locations, premium, cats, all_categories=False)) for s in shops
    ]


def only_mall(brief: ShopBrief, mall_id: int | None) -> ShopBrief:
    """The brief with only its locations in the mall (`None`: standalone addresses)."""
    kept = [loc for loc in brief.locations if (loc.mall.id if loc.mall else None) == mall_id]
    return brief.model_copy(update={"locations": kept})


async def load_detail(session: AsyncSession, shop: Shop, *, admin: bool = False) -> ShopDetail:
    premium = await _premium_ids(session, [shop.id])
    cats = await _categories_by_shop(session, [shop.id])
    locations = await _locations_by_shop(session, [shop.id], public=not admin)
    photos = await session.scalars(
        select(ShopPhoto.path).where(ShopPhoto.shop_id == shop.id).order_by(ShopPhoto.position)
    )
    fields = {
        **_brief_fields(shop, locations, premium, cats, all_categories=True),
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
