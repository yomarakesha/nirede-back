from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_or_404
from app.enums import ModerationStatus
from app.modules.moderation.models import ChangeRequest, EntityType
from app.modules.promotions.models import Promotion
from app.modules.promotions.schemas import PromotionUpdate
from app.modules.promotions.service import to_out, update_promotion
from app.modules.sellers.service import has_active_subscription
from app.modules.shops.models import Shop
from app.modules.shops.schemas import ShopFields, ShopUpdate
from app.modules.shops.service import load_detail, update_shop
from app.modules.users.models import User
from app.timeutil import utcnow

PAYLOAD_SCHEMAS: dict[EntityType, type[BaseModel]] = {
    EntityType.shop: ShopFields,
    EntityType.promotion: PromotionUpdate,
}


async def _owned_shop_id(
    session: AsyncSession, entity_type: EntityType, entity_id: int
) -> int | None:
    """Shop that owns the entity, or None when the entity no longer exists."""
    if entity_type == EntityType.shop:
        return entity_id if await session.get(Shop, entity_id) else None
    promo = await session.get(Promotion, entity_id)
    return promo.shop_id if promo else None


async def _edit_denied(session: AsyncSession, author_id: int, shop_id: int) -> str | None:
    """Why the author may not edit the shop right now, or None when they may."""
    shop = await session.get(Shop, shop_id)
    if shop is None:
        return "shop_not_found"
    if shop.owner_id != author_id:
        return "not_owner"
    if not await has_active_subscription(session, shop_id):
        return "subscription_required"
    return None


async def check_seller_can_edit(session: AsyncSession, author: User, shop_id: int) -> Shop:
    denied = await _edit_denied(session, author.id, shop_id)
    if denied == "shop_not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, denied)
    if denied is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, denied)
    return await session.get(Shop, shop_id)


async def submit_change_request(
    session: AsyncSession,
    author: User,
    entity_type: EntityType,
    entity_id: int,
    changes: BaseModel,
) -> ChangeRequest:
    payload = changes.model_dump(mode="json", exclude_unset=True)
    if not payload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty_change")
    shop_id = await _owned_shop_id(session, entity_type, entity_id)
    if shop_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity_type}_not_found")
    await check_seller_can_edit(session, author, shop_id)

    # A payload the admin may already be reading never changes: supersede it with a new request.
    previous = await session.scalar(
        select(ChangeRequest)
        .where(
            ChangeRequest.entity_type == entity_type,
            ChangeRequest.entity_id == entity_id,
            ChangeRequest.author_id == author.id,
            ChangeRequest.status == ModerationStatus.pending,
        )
        .with_for_update()
    )
    if previous is not None:
        previous.status = ModerationStatus.rejected
        previous.admin_comment = "superseded"
        previous.reviewed_at = utcnow()
        await session.flush()
    cr = ChangeRequest(
        entity_type=entity_type, entity_id=entity_id, author_id=author.id, payload=payload
    )
    session.add(cr)
    await session.commit()
    return cr


async def get_change_request_or_404(
    session: AsyncSession, cr_id: int, *, lock: bool = False
) -> ChangeRequest:
    return await get_or_404(session, ChangeRequest, cr_id, "change_request_not_found", lock=lock)


def _close(cr: ChangeRequest, admin: User, new_status: ModerationStatus, comment: str | None):
    cr.status = new_status
    cr.admin_comment = comment
    cr.reviewed_by = admin.id
    cr.reviewed_at = utcnow()


def _ensure_pending(cr: ChangeRequest) -> None:
    if cr.status != ModerationStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_reviewed")


async def _apply(session: AsyncSession, cr: ChangeRequest, data: BaseModel) -> None:
    if cr.entity_type == EntityType.shop:
        shop = await session.get(Shop, cr.entity_id)
        await update_shop(
            session, shop, ShopUpdate(**data.model_dump(exclude_unset=True)), commit=False
        )
    else:
        promo = await session.get(Promotion, cr.entity_id)
        await update_promotion(session, promo, data, commit=False)


async def approve_change_request(
    session: AsyncSession, cr: ChangeRequest, admin: User
) -> ChangeRequest:
    """Apply the change. If it can no longer be applied, reject it with the reason instead."""
    _ensure_pending(cr)
    shop_id = await _owned_shop_id(session, cr.entity_type, cr.entity_id)
    if shop_id is None:
        reason = "entity_deleted"
    else:
        reason = await _edit_denied(session, cr.author_id, shop_id)
        if reason == "subscription_required":
            reason = "subscription_expired"  # it was active when the request was submitted
    if reason is None:
        try:
            data = PAYLOAD_SCHEMAS[cr.entity_type].model_validate(cr.payload)
            async with session.begin_nested():
                await _apply(session, cr, data)
        except (ValidationError, IntegrityError):
            reason = "invalid_payload"
        except HTTPException as exc:
            reason = str(exc.detail)
    _close(cr, admin, ModerationStatus.rejected if reason else ModerationStatus.approved, reason)
    await session.commit()
    return cr


async def reject_change_request(
    session: AsyncSession, cr: ChangeRequest, admin: User, comment: str
) -> ChangeRequest:
    _ensure_pending(cr)
    _close(cr, admin, ModerationStatus.rejected, comment)
    await session.commit()
    return cr


async def current_snapshot(session: AsyncSession, cr: ChangeRequest) -> dict[str, Any] | None:
    if cr.entity_type == EntityType.shop:
        shop = await session.get(Shop, cr.entity_id)
        return (
            (await load_detail(session, shop, admin=True)).model_dump(mode="json") if shop else None
        )
    promo = await session.get(Promotion, cr.entity_id)
    return (await to_out(session, [promo]))[0].model_dump(mode="json") if promo else None
