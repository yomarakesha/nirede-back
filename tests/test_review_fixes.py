"""Regression tests for findings of the final branch review."""

from datetime import timedelta

from sqlalchemy import insert, select, update

from app.modules.notifications.models import Notification
from app.modules.notifications.service import notify_promotion_published
from app.modules.shops.models import Shop
from app.modules.users.models import OtpCode, favorite_shops
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


# Important 1: explicit null on non-nullable fields is 422, never 500.
async def test_change_request_null_name_422(client, seller_world):
    w = seller_world
    r = await client.post(
        f"/api/v1/seller/shops/{w.shop.id}/change-requests", json={"name": None}, headers=w.sh
    )
    assert r.status_code == 422


async def test_admin_patch_shop_null_name_422(client, seller_world):
    w = seller_world
    r = await client.patch(f"/api/v1/admin/shops/{w.shop.id}", json={"name": None}, headers=w.ah)
    assert r.status_code == 422


async def test_admin_patch_promotion_null_start_422(client, session, seller_world):
    w = seller_world
    promo = await make_promotion(session, w.shop)
    r = await client.patch(
        f"/api/v1/admin/promotions/{promo.id}", json={"starts_at": None}, headers=w.ah
    )
    assert r.status_code == 422


async def test_admin_patch_city_and_category_null_422(client, session):
    from tests.factories import make_category

    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    cat = await make_category(session, "X")
    r = await client.patch(f"/api/v1/admin/cities/{city.id}", json={"name_ru": None}, headers=h)
    assert r.status_code == 422
    r = await client.patch(f"/api/v1/admin/categories/{cat.id}", json={"name_ru": None}, headers=h)
    assert r.status_code == 422


async def test_nullable_fields_can_be_cleared(client, seller_world):
    w = seller_world
    r = await client.patch(
        f"/api/v1/admin/shops/{w.shop.id}", json={"how_to_find_ru": None}, headers=w.ah
    )
    assert r.status_code == 200
    assert r.json()["how_to_find_ru"] is None


# Important 2: admin photo/floor replacement on an inactive mall answers 200.
async def test_admin_photos_on_inactive_mall(client, session):
    h = auth_headers(await make_admin(session))
    mall = await make_mall(session, await make_city(session), is_active=False)
    r = await client.put(
        f"/api/v1/admin/malls/{mall.id}/photos", json={"paths": ["a.webp"]}, headers=h
    )
    assert r.status_code == 200
    r = await client.put(
        f"/api/v1/admin/malls/{mall.id}/floors",
        json=[{"number": 1, "summary_ru": "a", "summary_tk": "a"}],
        headers=h,
    )
    assert r.status_code == 200


# Important 3: promotions of hidden shops do not notify.
async def test_hidden_shop_promotion_no_notification(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    shop.is_active = False
    await session.flush()
    assert await notify_promotion_published(session, await make_promotion(session, shop)) == []


# Important 4: moving a mall to another city moves its shops; layout changes cannot break shops.
async def test_mall_city_change_moves_shops(client, session):
    h = auth_headers(await make_admin(session))
    a = await make_city(session)
    b = await make_city(session, "Мары", "Mary")
    mall = await make_mall(session, a)
    shop = await make_shop(session, "X", mall=mall, floor=1)
    r = await client.patch(f"/api/v1/admin/malls/{mall.id}", json={"city_id": b.id}, headers=h)
    assert r.status_code == 200
    await session.refresh(shop)
    assert shop.city_id == b.id


async def test_mall_floors_cannot_shrink_below_shops(client, session):
    h = auth_headers(await make_admin(session))
    mall = await make_mall(session, await make_city(session), floors_count=4)
    await make_shop(session, "X", mall=mall, floor=4)
    r = await client.patch(f"/api/v1/admin/malls/{mall.id}", json={"floors_count": 3}, headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "mall_has_shops_outside_layout"
    r = await client.patch(f"/api/v1/admin/malls/{mall.id}", json={"layout": "rows"}, headers=h)
    assert r.status_code == 409


# Important 5: future promotions are announced once they start.
async def test_announce_due_promotions(session):
    from app.cli import announce_due

    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    now = utcnow()
    promo = await make_promotion(
        session, shop, starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=5)
    )
    assert await notify_promotion_published(session, promo) == []
    await session.execute(update(promo.__class__).values(starts_at=now - timedelta(minutes=1)))
    await session.refresh(promo)
    assert await announce_due(session) == 1
    assert await announce_due(session) == 0  # never twice
    count = len(list(await session.scalars(select(Notification))))
    assert count == 1


async def test_promotion_announced_once_on_approve(session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city)
    user = await make_user(session)
    await session.execute(insert(favorite_shops).values(user_id=user.id, shop_id=shop.id))
    promo = await make_promotion(session, shop)
    assert len(await notify_promotion_published(session, promo)) == 1
    assert await notify_promotion_published(session, promo) == []


# Important 6: approval re-checks that the author still owns the shop.
async def test_approve_after_ownership_change_autorejects(client, session, seller_world):
    w = seller_world
    cr = (
        await client.post(
            f"/api/v1/seller/shops/{w.shop.id}/change-requests",
            json={"how_to_find_ru": "чужое"},
            headers=w.sh,
        )
    ).json()
    other = await make_user(session, phone="+99365000055", role="seller")
    await session.execute(update(Shop).where(Shop.id == w.shop.id).values(owner_id=other.id))
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "not_owner"


# Important 7: daily cap on OTP requests limits brute force.
async def test_daily_otp_cap(client, session, sms):
    for _ in range(10):
        r = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
        assert r.status_code == 204
        await session.execute(
            update(OtpCode).values(created_at=OtpCode.created_at - timedelta(hours=2))
        )
    r = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    assert r.status_code == 409
    assert r.json()["detail"] == "otp_rate_limited"


# Minor 1 (re-graded): a repeated approve of a new-shop application creates one shop.
async def test_application_approve_twice_one_shop(client, session):
    h = auth_headers(await make_admin(session))
    user = await make_user(session)
    mall = await make_mall(session, await make_city(session))
    r = await client.post(
        "/api/v1/me/seller-applications",
        json={
            "shop_name": "S",
            "mall_id": mall.id,
            "floor": 1,
            "number": "1",
            "contact_phone": "865123456",
        },
        headers=auth_headers(user),
    )
    app_id = r.json()["id"]
    body = {"shop": {"name": "S", "mall_id": mall.id, "floor": 1, "number": "1"}}
    first = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json=body, headers=h
    )
    second = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json=body, headers=h
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(list(await session.scalars(select(Shop)))) == 1
