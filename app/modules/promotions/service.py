from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_or_404
from app.enums import ModerationStatus
from app.modules.promotions.models import Promotion, active_clause
from app.modules.promotions.schemas import (
    PromotionFields,
    PromotionOut,
    PromotionsFeed,
    PromotionUpdate,
)
from app.modules.shops.models import Shop, premium_clause
from app.modules.shops.service import get_shop_or_404, load_briefs, public_shops
from app.modules.users.models import User
from app.timeutil import utcnow


async def get_promotion_or_404(session: AsyncSession, promo_id: int) -> Promotion:
    return await get_or_404(session, Promotion, promo_id, "promotion_not_found")


def is_active(promo: Promotion) -> bool:
    now = utcnow()
    return promo.status == ModerationStatus.approved and promo.starts_at <= now < promo.ends_at


async def create_promotion(
    session: AsyncSession,
    shop: Shop,
    data: PromotionFields,
    author: User,
    *,
    approved: bool,
) -> Promotion:
    promo = Promotion(
        **data.model_dump(exclude={"shop_id"}),
        shop_id=shop.id,
        created_by=author.id,
        status=ModerationStatus.approved if approved else ModerationStatus.pending,
    )
    session.add(promo)
    await session.commit()
    return promo


async def update_promotion(
    session: AsyncSession, promo: Promotion, data: PromotionUpdate, *, commit: bool = True
) -> Promotion:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(promo, field, value)
    if promo.ends_at <= promo.starts_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "ends_before_starts")
    if commit:
        await session.commit()
    return promo


async def set_status(
    session: AsyncSession,
    promo: Promotion,
    new_status: ModerationStatus,
    comment: str | None = None,
) -> bool:
    """Review a pending promotion. Returns True when it became publicly active by this call."""
    if promo.status != ModerationStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_reviewed")
    promo.status = new_status
    promo.admin_comment = comment
    await session.commit()
    return is_active(promo)


async def to_out(session: AsyncSession, promos: list[Promotion]) -> list[PromotionOut]:
    shops = list(
        await session.scalars(select(Shop).where(Shop.id.in_({p.shop_id for p in promos})))
    )
    briefs = {b.id: b for b in await load_briefs(session, shops)}
    return [
        PromotionOut(
            **{c: getattr(p, c) for c in PromotionOut.model_fields if c != "shop"},
            shop=briefs[p.shop_id],
        )
        for p in promos
    ]


def _public(city_id: int | None, mall_id: int | None) -> Select:
    visible = public_shops().with_only_columns(Shop.id)
    if city_id is not None:
        visible = visible.where(Shop.city_id == city_id)
    if mall_id is not None:
        visible = visible.where(Shop.mall_id == mall_id)
    return select(Promotion).where(active_clause(utcnow()), Promotion.shop_id.in_(visible))


async def feed(session: AsyncSession, city_id: int | None, mall_id: int | None) -> PromotionsFeed:
    stmt = _public(city_id, mall_id)
    featured = await session.scalar(
        stmt.join(Shop, Shop.id == Promotion.shop_id)
        .where(premium_clause(utcnow()))
        .order_by(Promotion.starts_at.desc(), Promotion.id.desc())
        .limit(1)
    )
    if featured is not None:
        stmt = stmt.where(Promotion.id != featured.id)
    items = list(await session.scalars(stmt.order_by(Promotion.ends_at, Promotion.id)))
    out = await to_out(session, ([featured] if featured else []) + items)
    return PromotionsFeed(featured=out[0] if featured else None, items=out[1:] if featured else out)


async def shop_for_promotion(session: AsyncSession, shop_id: int) -> Shop:
    return await get_shop_or_404(session, shop_id, public=False)
