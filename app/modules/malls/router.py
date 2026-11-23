from fastapi import APIRouter
from sqlalchemy import select

from app.deps import SessionDep
from app.modules.malls import service
from app.modules.malls.models import Mall
from app.modules.malls.schemas import MallDetail, MallListItem

router = APIRouter(prefix="/malls", tags=["malls"])


@router.get("")
async def list_malls(session: SessionDep, city_id: int | None = None) -> list[MallListItem]:
    stmt = select(Mall).where(Mall.is_active).order_by(Mall.sort_order, Mall.id)
    if city_id is not None:
        stmt = stmt.where(Mall.city_id == city_id)
    return await service.to_list_items(session, list(await session.scalars(stmt)))


@router.get("/{mall_id}")
async def get_mall(mall_id: int, session: SessionDep) -> MallDetail:
    return await service.to_detail(session, mall_id)
