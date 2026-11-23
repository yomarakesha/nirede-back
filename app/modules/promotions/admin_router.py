from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy import select

from app.crud import paginate
from app.deps import AdminUser, SessionDep
from app.enums import ModerationStatus
from app.modules.notifications.router import PushDep
from app.modules.notifications.service import announce_promotion
from app.modules.promotions import service
from app.modules.promotions.models import Promotion
from app.modules.promotions.schemas import (
    PromotionCreate,
    PromotionOut,
    PromotionUpdate,
    ReviewIn,
)
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/promotions", tags=["admin: promotions"])


async def _out(session, promo: Promotion) -> PromotionOut:
    return (await service.to_out(session, [promo]))[0]


@router.get("")
async def list_promotions(
    _: AdminUser,
    session: SessionDep,
    page: PageDep,
    status: ModerationStatus | None = None,
    shop_id: int | None = None,
) -> Page[PromotionOut]:
    stmt = select(Promotion).order_by(Promotion.id.desc())
    if status is not None:
        stmt = stmt.where(Promotion.status == status)
    if shop_id is not None:
        stmt = stmt.where(Promotion.shop_id == shop_id)
    items, total = await paginate(session, stmt, page)
    return Page(items=await service.to_out(session, items), total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_promotion(
    body: PromotionCreate,
    admin: AdminUser,
    session: SessionDep,
    background: BackgroundTasks,
    push: PushDep,
) -> PromotionOut:
    shop = await service.shop_for_promotion(session, body.shop_id)
    promo = await service.create_promotion(session, shop, body, admin, approved=True)
    await announce_promotion(session, promo, background, push)
    return await _out(session, promo)


@router.get("/{promo_id}")
async def get_promotion(promo_id: int, _: AdminUser, session: SessionDep) -> PromotionOut:
    return await _out(session, await service.get_promotion_or_404(session, promo_id))


@router.patch("/{promo_id}")
async def update_promotion(
    promo_id: int, body: PromotionUpdate, _: AdminUser, session: SessionDep
) -> PromotionOut:
    promo = await service.get_promotion_or_404(session, promo_id)
    await service.update_promotion(session, promo, body)
    return await _out(session, promo)


@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promotion(promo_id: int, _: AdminUser, session: SessionDep) -> None:
    await session.delete(await service.get_promotion_or_404(session, promo_id))
    await session.commit()


@router.post("/{promo_id}/approve")
async def approve(
    promo_id: int, _: AdminUser, session: SessionDep, background: BackgroundTasks, push: PushDep
) -> PromotionOut:
    promo = await service.get_promotion_or_404(session, promo_id)
    if await service.set_status(session, promo, ModerationStatus.approved):
        await announce_promotion(session, promo, background, push)
    return await _out(session, promo)


@router.post("/{promo_id}/reject")
async def reject(promo_id: int, body: ReviewIn, _: AdminUser, session: SessionDep) -> PromotionOut:
    promo = await service.get_promotion_or_404(session, promo_id)
    await service.set_status(session, promo, ModerationStatus.rejected, body.comment)
    return await _out(session, promo)
