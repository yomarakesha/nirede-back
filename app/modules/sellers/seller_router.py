from fastapi import APIRouter, status
from sqlalchemy import select

from app.deps import SellerUser, SessionDep
from app.modules.moderation import service as moderation
from app.modules.moderation.models import ChangeRequest, EntityType
from app.modules.moderation.schemas import ChangeRequestOut
from app.modules.promotions import service as promotions
from app.modules.promotions.models import Promotion
from app.modules.promotions.schemas import PromotionFields, PromotionOut, PromotionUpdate
from app.modules.shops.models import Shop
from app.modules.shops.schemas import ShopFields

router = APIRouter(prefix="/seller", tags=["seller"])


@router.post("/shops/{shop_id}/change-requests", status_code=status.HTTP_201_CREATED)
async def request_shop_change(
    shop_id: int, body: ShopFields, user: SellerUser, session: SessionDep
) -> ChangeRequestOut:
    cr = await moderation.submit_change_request(session, user, EntityType.shop, shop_id, body)
    return ChangeRequestOut.model_validate(cr)


@router.get("/change-requests")
async def my_change_requests(user: SellerUser, session: SessionDep) -> list[ChangeRequestOut]:
    rows = await session.scalars(
        select(ChangeRequest)
        .where(ChangeRequest.author_id == user.id)
        .order_by(ChangeRequest.id.desc())
    )
    return [ChangeRequestOut.model_validate(cr) for cr in rows]


@router.post("/shops/{shop_id}/promotions", status_code=status.HTTP_201_CREATED)
async def create_promotion(
    shop_id: int, body: PromotionFields, user: SellerUser, session: SessionDep
) -> PromotionOut:
    shop = await moderation.check_seller_can_edit(session, user, shop_id)
    promo = await promotions.create_promotion(session, shop, body, user, approved=False)
    return (await promotions.to_out(session, [promo]))[0]


@router.get("/promotions")
async def my_promotions(user: SellerUser, session: SessionDep) -> list[PromotionOut]:
    rows = await session.scalars(
        select(Promotion)
        .join(Shop, Shop.id == Promotion.shop_id)
        .where(Shop.owner_id == user.id)
        .order_by(Promotion.id.desc())
    )
    return await promotions.to_out(session, list(rows))


@router.post("/promotions/{promo_id}/change-requests", status_code=status.HTTP_201_CREATED)
async def request_promotion_change(
    promo_id: int, body: PromotionUpdate, user: SellerUser, session: SessionDep
) -> ChangeRequestOut:
    cr = await moderation.submit_change_request(session, user, EntityType.promotion, promo_id, body)
    return ChangeRequestOut.model_validate(cr)
