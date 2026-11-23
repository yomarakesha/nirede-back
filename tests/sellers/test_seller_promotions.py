from datetime import timedelta

from sqlalchemy import insert

from app.modules.users.models import favorite_shops
from app.timeutil import utcnow
from tests.factories import auth_headers, make_promotion, make_user


def _promo(**kw):
    now = utcnow()
    return {
        "title_ru": "−30% на пальто",
        "title_tk": "−30% paltolara",
        "badge": "−30%",
        "starts_at": (now - timedelta(minutes=5)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        **kw,
    }


async def test_seller_promotion_pending_until_admin_approves(client, session, seller_world):
    w = seller_world
    fan = await make_user(session, phone="+99365000099")
    await session.execute(insert(favorite_shops).values(user_id=fan.id, shop_id=w.shop.id))
    r = await client.post(
        f"/api/v1/seller/shops/{w.shop.id}/promotions", json=_promo(), headers=w.sh
    )
    assert r.status_code == 201, r.text
    promo = r.json()
    assert promo["status"] == "pending"
    assert (await client.get("/api/v1/promotions")).json()["featured"] is None
    mine = (await client.get("/api/v1/seller/promotions", headers=w.sh)).json()
    assert [p["id"] for p in mine] == [promo["id"]]

    r = await client.post(f"/api/v1/admin/promotions/{promo['id']}/approve", headers=w.ah)
    assert r.status_code == 200
    assert (await client.get("/api/v1/promotions")).json()["featured"]["id"] == promo["id"]
    feed = (await client.get("/api/v1/me/notifications", headers=auth_headers(fan))).json()
    assert feed["total"] == 1


async def test_seller_promotion_requires_subscription_and_ownership(client, session, seller_world):
    from tests.factories import make_shop

    w = seller_world
    free = await make_shop(session, "Free", mall=w.mall, floor=1, owner_id=w.seller.id)
    r = await client.post(f"/api/v1/seller/shops/{free.id}/promotions", json=_promo(), headers=w.sh)
    assert r.status_code == 403
    assert r.json()["detail"] == "subscription_required"
    stranger = await make_shop(session, "Stranger", mall=w.mall, floor=1)
    r = await client.post(
        f"/api/v1/seller/shops/{stranger.id}/promotions", json=_promo(), headers=w.sh
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "not_owner"


async def test_seller_promotion_change_request(client, session, seller_world):
    w = seller_world
    promo = await make_promotion(session, w.shop, "Старая")
    r = await client.post(
        f"/api/v1/seller/promotions/{promo.id}/change-requests",
        json={"title_ru": "Новая"},
        headers=w.sh,
    )
    assert r.status_code == 201, r.text
    cr = r.json()
    assert cr["entity_type"] == "promotion"
    assert (await client.get("/api/v1/promotions")).json()["featured"]["title_ru"] == "Старая"
    await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert (await client.get("/api/v1/promotions")).json()["featured"]["title_ru"] == "Новая"


async def test_promotion_change_bad_period_autorejects(client, session, seller_world):
    w = seller_world
    promo = await make_promotion(session, w.shop)
    past = (utcnow() - timedelta(days=30)).isoformat()
    cr = (
        await client.post(
            f"/api/v1/seller/promotions/{promo.id}/change-requests",
            json={"ends_at": past},
            headers=w.sh,
        )
    ).json()
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "ends_before_starts"
