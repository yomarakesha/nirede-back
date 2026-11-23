from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common import PhotoOut
from app.modules.malls.models import Mall, MallFloor, MallLayout, MallPhoto
from app.modules.malls.schemas import MallDetail, MallFloorIn, MallFloorOut, MallListItem
from app.timeutil import is_open, utcnow


async def get_mall_or_404(
    session: AsyncSession, mall_id: int, *, public: bool = False, with_children: bool = False
) -> Mall:
    stmt = select(Mall).where(Mall.id == mall_id)
    if public:
        stmt = stmt.where(Mall.is_active)
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


async def to_detail(session: AsyncSession, mall_id: int) -> MallDetail:
    mall = await get_mall_or_404(session, mall_id, public=True, with_children=True)
    return MallDetail(
        **MallListItem.model_validate(mall).model_dump(exclude={"cover", "cover_url"}),
        cover=mall.photos[0].path if mall.photos else None,
        city_id=mall.city_id,
        phone=mall.phone,
        photos=[PhotoOut(path=p.path) for p in mall.photos],
        floors=[MallFloorOut.model_validate(f) for f in mall.floors],
        is_open_now=is_open(mall.opens_at, mall.closes_at, utcnow()),
    )
