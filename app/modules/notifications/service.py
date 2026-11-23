from collections import defaultdict

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import delete, func, select, union, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.malls.models import Mall
from app.modules.notifications.models import DeviceToken, Notification
from app.modules.notifications.push import PushMessage, PushSender, send_all
from app.modules.promotions.models import Promotion
from app.modules.promotions.service import is_active
from app.modules.shops.models import Shop
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


async def notify_promotion_published(
    session: AsyncSession, promotion: Promotion
) -> list[Notification]:
    """Write feed entries for a promotion that is public now. Future ones are not announced."""
    if not is_active(promotion):
        return []
    shop = await session.get(Shop, promotion.shop_id)
    if shop is None:
        return []
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
    messages = await push_messages(session, notifications)
    if messages:
        background.add_task(send_all, messages, push)


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
