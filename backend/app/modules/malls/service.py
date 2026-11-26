from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common import PhotoOut
from app.crud import apply_update
from app.modules.categories.schemas import CategoryBrief
from app.modules.categories.service import ancestors_map
from app.modules.cities.models import City
from app.modules.cities.service import get_city_or_404
from app.modules.malls.models import Mall, MallFloor, MallLayout, MallPhoto
from app.modules.malls.schemas import (
    MallDetail,
    MallFloorIn,
    MallFloorOut,
    MallListItem,
    MallUpdate,
)
from app.timeutil import is_open, utcnow


def public_malls():
    """Active malls in active cities."""
    return select(Mall).join(City, City.id == Mall.city_id).where(Mall.is_active, City.is_active)


async def get_mall_or_404(
    session: AsyncSession, mall_id: int, *, public: bool = False, with_children: bool = False
) -> Mall:
    stmt = (public_malls() if public else select(Mall)).where(Mall.id == mall_id)
    if with_children:
        stmt = stmt.options(selectinload(Mall.photos), selectinload(Mall.floors))
        stmt = stmt.execution_options(populate_existing=True)
    mall = await session.scalar(stmt)
    if mall is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mall_not_found")
    return mall


def check_layout(mall: Mall) -> None:
    if mall.layout == MallLayout.floors and not mall.floors_count:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "floors_count_required")


async def check_shops_fit_layout(session: AsyncSession, mall: Mall) -> None:
    """Refuse a layout/floors change that would leave shop locations in the mall invalid."""
    from app.modules.shops.models import ShopLocation as Loc

    # Same rules as shops.service._to_location.
    if mall.layout == MallLayout.floors:
        broken = (
            Loc.floor.is_(None)
            | (Loc.floor < 1)
            | (Loc.floor > (mall.floors_count or 0))
            | Loc.row.is_not(None)
        )
    else:
        broken = Loc.row.is_(None) | (Loc.row == "") | Loc.floor.is_not(None)
    found = await session.scalar(select(Loc.id).where(Loc.mall_id == mall.id, broken).limit(1))
    if found is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "mall_has_shops_outside_layout")


async def sync_shop_city(session: AsyncSession, mall: Mall) -> None:
    """Shop locations in a mall always share the mall's city."""
    from app.modules.shops.models import ShopLocation

    await session.execute(
        update(ShopLocation).where(ShopLocation.mall_id == mall.id).values(city_id=mall.city_id)
    )


async def update_mall(session: AsyncSession, mall: Mall, data: MallUpdate) -> Mall:
    if data.city_id is not None:
        await get_city_or_404(session, data.city_id)
    apply_update(mall, data)
    check_layout(mall)
    await check_shops_fit_layout(session, mall)
    await sync_shop_city(session, mall)
    await session.commit()
    return mall


async def replace_photos(session: AsyncSession, mall: Mall, paths: list[str]) -> None:
    mall = await get_mall_or_404(session, mall.id, with_children=True)
    mall.photos = [MallPhoto(path=p, position=i) for i, p in enumerate(paths)]
    await session.commit()


async def replace_floors(session: AsyncSession, mall: Mall, floors: list[MallFloorIn]) -> None:
    numbers = [f.number for f in floors]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "duplicate_floor_number")
    mall = await get_mall_or_404(session, mall.id, with_children=True)
    mall.floors.clear()
    await session.flush()
    mall.floors.extend(MallFloor(**f.model_dump()) for f in floors)
    await session.commit()


async def covers(session: AsyncSession, mall_ids: list[int]) -> dict[int, str]:
    rows = await session.execute(
        select(MallPhoto.mall_id, MallPhoto.path)
        .where(MallPhoto.mall_id.in_(mall_ids))
        .order_by(MallPhoto.mall_id, MallPhoto.position)
    )
    result: dict[int, str] = {}
    for mall_id, path in rows:
        result.setdefault(mall_id, path)
    return result


async def to_list_items(session: AsyncSession, malls: list[Mall]) -> list[MallListItem]:
    cover_map = await covers(session, [m.id for m in malls])
    return [
        MallListItem.model_validate(m).model_copy(update={"cover": cover_map.get(m.id)})
        for m in malls
    ]


async def _shop_stats(session: AsyncSession, mall_id: int) -> tuple[int, list[CategoryBrief]]:
    # Imported here: shops depends on malls, not the other way round.
    from app.modules.shops.models import Shop, ShopLocation, shop_categories

    in_mall = select(ShopLocation.shop_id).where(ShopLocation.mall_id == mall_id)
    active = select(Shop.id).where(Shop.id.in_(in_mall), Shop.is_active)
    count = await session.scalar(select(func.count()).select_from(active.subquery())) or 0
    category_ids = list(
        await session.scalars(
            select(shop_categories.c.category_id)
            .where(shop_categories.c.shop_id.in_(active))
            .distinct()
        )
    )
    roots = {}
    for path in (await ancestors_map(session, category_ids)).values():
        if path and all(c.is_active for c in path):
            roots[path[0].id] = path[0]
    ordered = sorted(roots.values(), key=lambda c: (c.sort_order, c.id))
    return count, [CategoryBrief.model_validate(c) for c in ordered]


async def to_detail(session: AsyncSession, mall_id: int, *, public: bool = True) -> MallDetail:
    mall = await get_mall_or_404(session, mall_id, public=public, with_children=True)
    shop_count, root_categories = await _shop_stats(session, mall_id)
    return MallDetail(
        **MallListItem.model_validate(mall).model_dump(exclude={"cover", "cover_url"}),
        cover=mall.photos[0].path if mall.photos else None,
        city_id=mall.city_id,
        phone=mall.phone,
        photos=[PhotoOut(path=p.path) for p in mall.photos],
        floors=[MallFloorOut.model_validate(f) for f in mall.floors],
        is_open_now=is_open(mall.opens_at, mall.closes_at, utcnow()),
        shop_count=shop_count,
        root_categories=root_categories,
    )
