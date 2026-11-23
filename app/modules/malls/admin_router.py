from fastapi import APIRouter, status
from sqlalchemy import select

from app.common import PhotosIn
from app.crud import apply_update, delete_or_409, paginate
from app.deps import AdminUser, SessionDep
from app.modules.cities.service import get_city_or_404
from app.modules.malls import service
from app.modules.malls.models import Mall
from app.modules.malls.schemas import MallAdminOut, MallCreate, MallDetail, MallFloorIn, MallUpdate
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/malls", tags=["admin: malls"])


@router.get("")
async def list_malls(
    _: AdminUser, session: SessionDep, page: PageDep, city_id: int | None = None
) -> Page[MallAdminOut]:
    stmt = select(Mall).order_by(Mall.sort_order, Mall.id)
    if city_id is not None:
        stmt = stmt.where(Mall.city_id == city_id)
    items, total = await paginate(session, stmt, page)
    return Page(items=[MallAdminOut.model_validate(m) for m in items], total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_mall(body: MallCreate, _: AdminUser, session: SessionDep) -> MallAdminOut:
    await get_city_or_404(session, body.city_id)
    mall = Mall(**body.model_dump())
    session.add(mall)
    await session.commit()
    return MallAdminOut.model_validate(mall)


@router.get("/{mall_id}")
async def get_mall(mall_id: int, _: AdminUser, session: SessionDep) -> MallAdminOut:
    return MallAdminOut.model_validate(await service.get_mall_or_404(session, mall_id))


@router.patch("/{mall_id}")
async def update_mall(
    mall_id: int, body: MallUpdate, _: AdminUser, session: SessionDep
) -> MallAdminOut:
    mall = await service.get_mall_or_404(session, mall_id)
    if body.city_id is not None:
        await get_city_or_404(session, body.city_id)
    apply_update(mall, body)
    service.check_layout(mall)
    await service.check_shops_fit_layout(session, mall)
    await service.sync_shop_city(session, mall)
    await session.commit()
    return MallAdminOut.model_validate(mall)


@router.delete("/{mall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mall(mall_id: int, _: AdminUser, session: SessionDep) -> None:
    await delete_or_409(session, await service.get_mall_or_404(session, mall_id), "mall_in_use")


@router.put("/{mall_id}/photos")
async def replace_photos(
    mall_id: int, body: PhotosIn, _: AdminUser, session: SessionDep
) -> MallDetail:
    mall = await service.get_mall_or_404(session, mall_id)
    await service.replace_photos(session, mall, body.paths)
    return await service.to_detail(session, mall_id, public=False)


@router.put("/{mall_id}/floors")
async def replace_floors(
    mall_id: int, body: list[MallFloorIn], _: AdminUser, session: SessionDep
) -> MallDetail:
    mall = await service.get_mall_or_404(session, mall_id)
    await service.replace_floors(session, mall, body)
    return await service.to_detail(session, mall_id, public=False)
