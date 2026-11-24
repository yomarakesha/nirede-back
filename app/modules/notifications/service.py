from collections import defaultdict

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import delete, func, select, union, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.malls.models import Mall
from app.modules.notifications.models import DeviceToken, Notification
from app.modules.notifications.push import PushMessage, PushSender, send_all
from app.modules.promotions.models import Promotion, active_clause
from app.modules.promotions.service import is_active
from app.modules.shops.models import Shop
from app.modules.shops.service import public_shops
from app.modules.users.models import User, favorite_shops, user_malls
from app.timeutil import utcnow


async def _recipient_ids(session: AsyncSession, shop: Shop) -> list[int]:
    by_favorite = (
        select(favorite_shops.c.user_id)
        .join(User, User.id == favorite_shops.c.user_id)
        .where(favorite_shops.c.shop_id == shop.id, User.notify_favorite_shops)
    )
    queries = [by_favorite]
    if shop.mall_id is not None:
        queries.append(
            select(user_malls.c.user_id)
            .join(User, User.id == user_malls.c.user_id)
            .where(user_malls.c.mall_id == shop.mall_id, User.notify_my_malls)
        )
    return list(await session.scalars(union(*queries)))


async def _claim_announcement(session: AsyncSession, promotion: Promotion) -> bool:
    """Set `announced_at` unless someone already did. True when this call set it.

    The conditional UPDATE takes the row lock, so of two concurrent callers (approve and
    announce-due, or overlapping announce-due runs) only one wins; the other sees 0 rows
    once the winner commits.
    """
    announced_at = await session.scalar(
        update(Promotion)
        .where(Promotion.id == promotion.id, Promotion.announced_at.is_(None))
        .values(announced_at=utcnow())
        .returning(Promotion.announced_at)
        .execution_options(synchronize_session=False)
    )
    if announced_at is None:
        return False
    set_committed_value(promotion, "announced_at", announced_at)
    return True


async def notify_promotion_published(
    session: AsyncSession, promotion: Promotion
) -> list[Notification] | None:
    """Write feed entries for a promotion that is public now, once.

    Returns None when this call did not announce it: not active yet, shop hidden, or already
    announced. Promotions that start later are picked up by `announce_due`.
    """
    if not is_active(promotion) or promotion.announced_at is not None:
        return None
    shop = await session.scalar(public_shops().where(Shop.id == promotion.shop_id))
    if shop is None:
        return None
    if not await _claim_announcement(session, promotion):
        return None
    mall = await session.get(Mall, shop.mall_id) if shop.mall_id else None
    title_ru = mall.name_ru if mall else shop.name
    title_tk = mall.name_tk if mall else shop.name
    notifications = [
        Notification(
            user_id=user_id,
            promotion_id=promotion.id,
            title_ru=title_ru,
            title_tk=title_tk,
            body_ru=f"{shop.name}: {promotion.title_ru}",
            body_tk=f"{shop.name}: {promotion.title_tk}",
            image=promotion.image or shop.logo,
        )
        for user_id in await _recipient_ids(session, shop)
    ]
    session.add_all(notifications)
    await session.commit()
    return notifications


async def push_messages(
    session: AsyncSession, notifications: list[Notification]
) -> list[PushMessage]:
    """One message per (notification text, language) with all recipients' device tokens."""
    if not notifications:
        return []
    by_user = {n.user_id: n for n in notifications}
    rows = await session.execute(
        select(DeviceToken.token, User.id, User.language)
        .join(User, User.id == DeviceToken.user_id)
        .where(DeviceToken.user_id.in_(by_user))
    )
    grouped: dict[tuple[int, str], list[str]] = defaultdict(list)
    for token, user_id, language in rows:
        grouped[(user_id, language)].append(token)
    messages: dict[tuple[str, str], PushMessage] = {}
    for (user_id, language), tokens in grouped.items():
        n = by_user[user_id]
        title, body = getattr(n, f"title_{language}"), getattr(n, f"body_{language}")
        msg = messages.setdefault(
            (title, body), PushMessage([], title, body, {"promotion_id": n.promotion_id})
        )
        msg.tokens.extend(tokens)
    return list(messages.values())


async def announce_promotion(
    session: AsyncSession, promotion: Promotion, background: BackgroundTasks, push: PushSender
) -> None:
    notifications = await notify_promotion_published(session, promotion)
    messages = await push_messages(session, notifications or [])
    if messages:
        background.add_task(send_all, messages, push)


async def announce_due(session: AsyncSession, push: PushSender) -> int:
    """Announce approved promotions that have started but were not announced yet.

    Run periodically (`python -m app.cli announce-due`). A promotion of a hidden shop stays
    unannounced and is retried on the next run, so followers still hear about it if the shop
    becomes visible again before the promotion ends. Returns how many were announced.
    """
    due = list(
        await session.scalars(
            select(Promotion).where(active_clause(utcnow()), Promotion.announced_at.is_(None))
        )
    )
    announced = 0
    for promo in due:
        notifications = await notify_promotion_published(session, promo)
        if notifications is None:
            continue
        announced += 1
        await send_all(await push_messages(session, notifications), push)
    return announced


async def mark_read(session: AsyncSession, user: User, notification_id: int) -> None:
    result = await session.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .values(read_at=func.coalesce(Notification.read_at, utcnow()))
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification_not_found")
    await session.commit()


async def mark_all_read(session: AsyncSession, user: User) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    await session.commit()


async def unread_count(session: AsyncSession, user: User) -> int:
    stmt = select(func.count()).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    return await session.scalar(stmt) or 0


async def register_device(session: AsyncSession, user: User, token: str, platform: str) -> None:
    stmt = insert(DeviceToken).values(user_id=user.id, token=token, platform=platform)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DeviceToken.token],
        set_={"user_id": user.id, "platform": platform, "updated_at": func.now()},
    )
    await session.execute(stmt)
    await session.commit()


async def remove_device(session: AsyncSession, user: User, token: str) -> None:
    await session.execute(
        delete(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user.id)
    )
    await session.commit()
