from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_or_404
from app.enums import ModerationStatus, UserRole
from app.modules.sellers.models import SellerApplication
from app.modules.sellers.schemas import ApplicationIn, SellerShopOut, SubscriptionIn
from app.modules.shops.models import Shop, Subscription
from app.modules.shops.schemas import ShopCreate
from app.modules.shops.service import create_shop, get_shop_or_404, load_briefs
from app.modules.users.models import User
from app.timeutil import utcnow


async def submit_application(
    session: AsyncSession, user: User, data: ApplicationIn
) -> SellerApplication:
    pending = await session.scalar(
        select(SellerApplication.id).where(
            SellerApplication.user_id == user.id,
            SellerApplication.status == ModerationStatus.pending,
        )
    )
    if pending is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "application_pending")
    if data.shop_id is not None:
        await get_shop_or_404(session, data.shop_id, public=False)
    application = SellerApplication(user_id=user.id, **data.model_dump())
    session.add(application)
    await session.commit()
    return application


async def get_application_or_404(
    session: AsyncSession, app_id: int, *, lock: bool = False
) -> SellerApplication:
    return await get_or_404(session, SellerApplication, app_id, "application_not_found", lock=lock)


def _ensure_pending(application: SellerApplication) -> None:
    if application.status != ModerationStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_reviewed")


async def create_subscription(
    session: AsyncSession, shop: Shop, data: SubscriptionIn, admin: User, *, commit: bool = True
) -> Subscription:
    now = utcnow()
    latest_end = await session.scalar(
        select(func.max(Subscription.ends_at)).where(Subscription.shop_id == shop.id)
    )
    starts = max(now, latest_end) if latest_end else now
    subscription = Subscription(
        shop_id=shop.id,
        starts_at=starts,
        ends_at=starts + timedelta(days=data.days),
        amount=data.amount,
        activated_by=admin.id,
        note=data.note,
    )
    session.add(subscription)
    if commit:
        await session.commit()
    return subscription


async def has_active_subscription(session: AsyncSession, shop_id: int) -> bool:
    now = utcnow()
    found = await session.scalar(
        select(Subscription.id).where(
            Subscription.shop_id == shop_id,
            Subscription.starts_at <= now,
            Subscription.ends_at > now,
        )
    )
    return found is not None


async def approve_application(
    session: AsyncSession,
    application: SellerApplication,
    admin: User,
    *,
    shop_data: ShopCreate | None,
    subscription: SubscriptionIn | None,
) -> Shop:
    _ensure_pending(application)
    if application.shop_id is not None:
        shop = await get_shop_or_404(session, application.shop_id, public=False)
        if shop.owner_id is not None and shop.owner_id != application.user_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "shop_already_owned")
    elif shop_data is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "shop_data_required")
    else:
        shop = await create_shop(session, shop_data, commit=False)
        application.shop_id = shop.id

    shop.owner_id = application.user_id
    user = await session.get(User, application.user_id)
    if user is not None and user.role == UserRole.user:
        user.role = UserRole.seller
    if subscription is not None:
        await create_subscription(session, shop, subscription, admin, commit=False)
    application.status = ModerationStatus.approved
    application.reviewed_by = admin.id
    application.reviewed_at = utcnow()
    await session.commit()
    return shop


async def reject_application(
    session: AsyncSession, application: SellerApplication, admin: User, comment: str
) -> None:
    _ensure_pending(application)
    application.status = ModerationStatus.rejected
    application.admin_comment = comment
    application.reviewed_by = admin.id
    application.reviewed_at = utcnow()
    await session.commit()


async def pending_change_counts(session: AsyncSession, shop_ids: list[int]) -> dict[int, int]:
    # Imported here: moderation depends on this module.
    from app.modules.moderation.models import ChangeRequest, EntityType

    rows = await session.execute(
        select(ChangeRequest.entity_id, func.count())
        .where(
            ChangeRequest.entity_type == EntityType.shop,
            ChangeRequest.entity_id.in_(shop_ids),
            ChangeRequest.status == ModerationStatus.pending,
        )
        .group_by(ChangeRequest.entity_id)
    )
    return dict(rows.all())


async def seller_shops(session: AsyncSession, user: User) -> list[SellerShopOut]:
    shops = list(
        await session.scalars(select(Shop).where(Shop.owner_id == user.id).order_by(Shop.name))
    )
    ids = [s.id for s in shops]
    ends = dict(
        (
            await session.execute(
                select(Subscription.shop_id, func.max(Subscription.ends_at))
                .where(Subscription.shop_id.in_(ids))
                .group_by(Subscription.shop_id)
            )
        ).all()
    )
    pending = await pending_change_counts(session, ids)
    return [
        SellerShopOut(
            **brief.model_dump(exclude={"logo_url"}),
            subscription_ends_at=ends.get(brief.id),
            pending_change_requests=pending.get(brief.id, 0),
        )
        for brief in await load_briefs(session, shops)
    ]
