from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import SessionDep
from app.modules.categories.service import subtree_ids
from app.modules.malls.service import get_mall_or_404
from app.modules.shops import service
from app.modules.shops.models import Shop, shop_categories
from app.modules.shops.schemas import MallShopsOut, ShopDetail

router = APIRouter(tags=["shops"])


@router.get("/shops/{shop_id}")
async def get_shop(shop_id: int, session: SessionDep) -> ShopDetail:
    shop = await service.get_shop_or_404(session, shop_id, public=True)
    return await service.load_detail(session, shop)


@router.get("/malls/{mall_id}/shops")
async def mall_shops(
    mall_id: int,
    session: SessionDep,
    floor: int | None = None,
    row: str | None = None,
    category_id: int | None = None,
) -> MallShopsOut:
    await get_mall_or_404(session, mall_id, public=True)
    stmt = service.public_shops().where(Shop.mall_id == mall_id)
    if floor is not None:
        stmt = stmt.where(Shop.floor == floor)
    if row is not None:
        stmt = stmt.where(Shop.row == row)
    if category_id is not None:
        ids = await subtree_ids(session, category_id)
        stmt = stmt.where(
            Shop.id.in_(
                select(shop_categories.c.shop_id).where(shop_categories.c.category_id.in_(ids))
            )
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    shops = list(await session.scalars(service.order_premium_first(stmt)))
    return MallShopsOut(total=total, items=await service.load_briefs(session, shops))
