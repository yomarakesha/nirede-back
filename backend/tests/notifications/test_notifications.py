from datetime import timedelta

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.notifications.models import Notification
from app.modules.notifications.push import get_push_sender
from app.modules.notifications.service import announce_due, notify_promotion_published
from app.modules.promotions.models import Promotion
from app.modules.users.models import favorite_shops, user_malls
from app.timeutil import utcnow
from tests.factories import (
    auth_headers,
    make_admin,
    make_city,
    make_mall,
    make_promotion,
    make_shop,
    make_user,
)


class FakePush:
    def __init__(self):
        self.calls = []

    async def send(self, tokens, title, body, data):
        self.calls.append((tokens, title, body, data))


@pytest.fixture
def push(app):
    fake = FakePush()
    app.dependency_overrides[get_push_sender] = lambda: fake
    return fake


async def _world(session):
    city = await make_city(session)
    mall = await make_mall(session, city, "Беркарар", name_tk="Berkarar")
    shop = await make_shop(session, "Moda Line", mall=mall, floor=2, number="214")
    return mall, shop


async def _fav(session, user, shop):
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))


async def _my_mall(session, user, mall):
    await session.execute(insert(user_malls).values(user_id=user.id, mall_id=mall.id))


async def _recipients(session, promo):
    return sorted(n.user_id for n in await notify_promotion_published(session, promo))


async def test_fanout_favorites_and_malls(session):
    mall, shop = await _world(session)
    u1 = await make_user(session, phone="+99365000001")
    u2 = await make_user(session, phone="+99365000002")
    await make_user(session, phone="+99365000003")
    await _fav(session, u1, shop)
    await _my_mall(session, u2, mall)
    promo = await make_promotion(session, shop, "−30% на пальто и пуховики")
    assert await _recipients(session, promo) == sorted([u1.id, u2.id])
    n = await session.scalar(select(Notification).where(Notification.user_id == u1.id))
    assert n.title_ru == "Беркарар"
    assert n.body_ru == "Moda Line: −30% на пальто и пуховики"
    assert n.promotion_id == promo.id


async def test_user_with_both_gets_one(session):
    mall, shop = await _world(session)
    u = await make_user(session)
    await _fav(session, u, shop)
    await _my_mall(session, u, mall)
    promo = await make_promotion(session, shop)
    assert await _recipients(session, promo) == [u.id]


async def test_respects_toggles(session):
    mall, shop = await _world(session)
    fav_off = await make_user(session, phone="+99365000001", notify_favorite_shops=False)
    mall_off = await make_user(session, phone="+99365000002", notify_my_malls=False)
    await _fav(session, fav_off, shop)
    await _my_mall(session, mall_off, mall)
    promo = await make_promotion(session, shop)
    assert await _recipients(session, promo) == []


async def test_future_promotion_no_notification(session):
    _, shop = await _world(session)
    u = await make_user(session)
    await _fav(session, u, shop)
    now = utcnow()
    promo = await make_promotion(
        session, shop, starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=5)
    )
    assert await notify_promotion_published(session, promo) is None


async def test_standalone_shop_title_is_shop_name(session):
    city = await make_city(session)
    shop = await make_shop(session, "Город Пальто", city=city)
    u = await make_user(session)
    await _fav(session, u, shop)
    [n] = await notify_promotion_published(session, await make_promotion(session, shop, "Скидки"))
    assert n.title_ru == "Город Пальто"


async def test_admin_approve_triggers_notification(client, session, push):
    h = auth_headers(await make_admin(session))
    _, shop = await _world(session)
    user = await make_user(session, language="tk")
    await _fav(session, user, shop)
    uh = auth_headers(user)
    r = await client.post(
        "/api/v1/me/devices", json={"token": "tok-1", "platform": "android"}, headers=uh
    )
    assert r.status_code == 204
    promo = await make_promotion(session, shop, "−30%", title_tk="−30% paltolara", status="pending")
    r = await client.post(f"/api/v1/admin/promotions/{promo.id}/approve", headers=h)
    assert r.status_code == 200
    assert len(push.calls) == 1
    tokens, title, body, data = push.calls[0]
    assert tokens == ["tok-1"]
    assert title == "Berkarar"
    assert body == "Moda Line: −30% paltolara"
    assert data["promotion_id"] == promo.id


async def test_admin_create_triggers_notification(client, session, push):
    h = auth_headers(await make_admin(session))
    _, shop = await _world(session)
    user = await make_user(session)
    await _fav(session, user, shop)
    now = utcnow()
    r = await client.post(
        "/api/v1/admin/promotions",
        json={
            "shop_id": shop.id,
            "title_ru": "Скидка",
            "title_tk": "Arzanladyş",
            "badge": "−10%",
            "starts_at": (now - timedelta(minutes=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
        },
        headers=h,
    )
    assert r.status_code == 201
    r = await client.get("/api/v1/me/notifications", headers=auth_headers(user))
    assert r.json()["total"] == 1


async def test_feed_read_flow(client, session):
    _, shop = await _world(session)
    user = await make_user(session)
    other = await make_user(session, phone="+99365000009")
    await _fav(session, user, shop)
    await _fav(session, other, shop)
    await notify_promotion_published(session, await make_promotion(session, shop, "A"))
    await notify_promotion_published(session, await make_promotion(session, shop, "B"))
    h = auth_headers(user)
    feed = (await client.get("/api/v1/me/notifications", headers=h)).json()
    assert feed["total"] == 2
    assert feed["items"][0]["body_ru"] == "Moda Line: B"
    assert feed["items"][0]["read_at"] is None
    count = lambda: client.get("/api/v1/me/notifications/unread-count", headers=h)  # noqa: E731
    assert (await count()).json() == {"count": 2}
    first = feed["items"][0]["id"]
    assert (
        await client.post(f"/api/v1/me/notifications/{first}/read", headers=h)
    ).status_code == 204
    assert (await count()).json() == {"count": 1}
    assert (await client.post("/api/v1/me/notifications/read-all", headers=h)).status_code == 204
    assert (await count()).json() == {"count": 0}
    theirs = (await client.get("/api/v1/me/notifications", headers=auth_headers(other))).json()
    r = await client.post(f"/api/v1/me/notifications/{theirs['items'][0]['id']}/read", headers=h)
    assert r.status_code == 404


async def test_device_token_moves_between_users(client, session):
    a = auth_headers(await make_user(session, phone="+99365000001"))
    b_user = await make_user(session, phone="+99365000002")
    b = auth_headers(b_user)
    body = {"token": "shared", "platform": "ios"}
    assert (await client.post("/api/v1/me/devices", json=body, headers=a)).status_code == 204
    assert (await client.post("/api/v1/me/devices", json=body, headers=b)).status_code == 204
    from app.modules.notifications.models import DeviceToken

    token = await session.scalar(select(DeviceToken).where(DeviceToken.token == "shared"))
    assert token.user_id == b_user.id
    assert (await client.delete("/api/v1/me/devices/shared", headers=a)).status_code == 204
    assert await session.scalar(select(DeviceToken).where(DeviceToken.token == "shared"))
    assert (await client.delete("/api/v1/me/devices/shared", headers=b)).status_code == 204
    assert await session.scalar(select(DeviceToken).where(DeviceToken.token == "shared")) is None


async def test_hidden_shop_promotion_no_notification(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    shop.is_active = False
    await session.flush()
    assert await notify_promotion_published(session, await make_promotion(session, shop)) is None


async def test_promotion_announced_once_on_approve(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    promo = await make_promotion(session, shop)
    assert len(await notify_promotion_published(session, promo)) == 1
    assert await notify_promotion_published(session, promo) is None


async def test_concurrent_announce_writes_once(session):
    """A caller holding a stale copy (announced_at still None) must not announce again."""
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    promo = await make_promotion(session, shop)
    assert len(await notify_promotion_published(session, promo)) == 1
    set_committed_value(promo, "announced_at", None)  # what a concurrent worker saw
    assert await notify_promotion_published(session, promo) is None
    assert len(list(await session.scalars(select(Notification)))) == 1


async def test_announce_due_promotions(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    now = utcnow()
    promo = await make_promotion(
        session, shop, starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=5)
    )
    assert await notify_promotion_published(session, promo) is None
    await session.execute(update(Promotion).values(starts_at=now - timedelta(minutes=1)))
    await session.refresh(promo)
    push = FakePush()
    assert await announce_due(session, push) == 1
    assert await announce_due(session, push) == 0  # never twice
    count = len(list(await session.scalars(select(Notification))))
    assert count == 1


async def test_announce_due_retries_hidden_shop(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    shop.is_active = False
    await session.flush()
    promo = await make_promotion(session, shop)
    push = FakePush()
    assert await announce_due(session, push) == 0
    assert promo.announced_at is None
    shop.is_active = True
    await session.flush()
    assert await announce_due(session, push) == 1
    assert len(list(await session.scalars(select(Notification)))) == 1
