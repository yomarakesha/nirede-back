from fastapi import APIRouter

from app.deps import SessionDep
from app.modules.promotions import service
from app.modules.promotions.schemas import PromotionsFeed

router = APIRouter(prefix="/promotions", tags=["promotions"])


@router.get("")
async def list_promotions(
    session: SessionDep, city_id: int | None = None, mall_id: int | None = None
) -> PromotionsFeed:
    return await service.feed(session, city_id, mall_id)
