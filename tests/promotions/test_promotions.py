from datetime import timedelta

from app.timeutil import utcnow
from tests.factories import (
    auth_headers,
    make_admin,
    make_city,
    make_mall,
    make_promotion,
    make_shop,
)


async def _world(session):
    city = await make_city(session)
    berkarar = await make_mall(session, city, "Беркарар")
    arkach = await make_mall(session, city, "Аркач")
    moda = await make_shop(session, "Moda Line", mall=berkarar, floor=2, number="214", premium=True)
    zamana = await make_shop(session, "Zamana", mall=arkach, floor=1, number="24")
    return berkarar, arkach, moda, zamana


def _body(shop_id, **kw):
    now = utcnow()
    return {
        "shop_id": shop_id,
        "title_ru": "Шубы и пальто",
        "title_tk": "Şubalar we paltolar",
        "badge": "−25%",
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        **kw,
    }


async def test_admin_created_is_public(client, session):
    h = auth_headers(await make_admin(session))
    _, _, _, zamana = await _world(session)
    r = await client.post("/api/v1/admin/promotions", json=_body(zamana.id), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "approved"
    body = (await client.get("/api/v1/promotions")).json()
    assert [p["title_ru"] for p in body["items"]] == ["Шубы и пальто"]
    assert body["items"][0]["shop"]["name"] == "Zamana"


async def test_pending_not_public(client, session):
    _, _, _, zamana = await _world(session)
    await make_promotion(session, zamana, status="pending")
    body = (await client.get("/api/v1/promotions")).json()
    assert body == {"featured": None, "items": []}


async def test_expired_and_future_hidden(client, session):
    _, _, _, zamana = await _world(session)
    now = utcnow()
    await make_promotion(
        session, zamana, "old", starts_at=now - timedelta(days=9), ends_at=now - timedelta(days=1)
    )
    await make_promotion(
        session, zamana, "soon", starts_at=now + timedelta(days=1), ends_at=now + timedelta(days=9)
    )
    await make_promotion(session, zamana, "now")
    body = (await client.get("/api/v1/promotions")).json()
    assert [p["title_ru"] for p in body["items"]] == ["now"]


async def test_featured_is_premium_shop_promo(client, session):
    _, _, moda, zamana = await _world(session)
    await make_promotion(session, zamana, "Трикотаж")
    await make_promotion(session, moda, "−30% на пальто и пуховики")
    body = (await client.get("/api/v1/promotions")).json()
    assert body["featured"]["title_ru"] == "−30% на пальто и пуховики"
    assert body["featured"]["shop"]["is_premium"] is True
    assert [p["title_ru"] for p in body["items"]] == ["Трикотаж"]


async def test_items_ordered_by_end(client, session):
    _, _, _, zamana = await _world(session)
    now = utcnow()
    await make_promotion(session, zamana, "late", ends_at=now + timedelta(days=20))
    await make_promotion(session, zamana, "early", ends_at=now + timedelta(days=2))
    body = (await client.get("/api/v1/promotions")).json()
    assert [p["title_ru"] for p in body["items"]] == ["early", "late"]


async def test_filter_by_mall(client, session):
    berkarar, arkach, moda, zamana = await _world(session)
    await make_promotion(session, moda, "A")
    await make_promotion(session, zamana, "B")
    body = (await client.get("/api/v1/promotions", params={"mall_id": arkach.id})).json()
    assert body["featured"] is None
    assert [p["title_ru"] for p in body["items"]] == ["B"]


async def test_inactive_shop_promo_hidden(client, session):
    _, _, _, zamana = await _world(session)
    await make_promotion(session, zamana)
    zamana.is_active = False
    await session.flush()
    assert (await client.get("/api/v1/promotions")).json()["items"] == []


async def test_ends_before_starts_422(client, session):
    h = auth_headers(await make_admin(session))
    _, _, _, zamana = await _world(session)
    now = utcnow()
    body = _body(
        zamana.id, starts_at=now.isoformat(), ends_at=(now - timedelta(days=1)).isoformat()
    )
    r = await client.post("/api/v1/admin/promotions", json=body, headers=h)
    assert r.status_code == 422


async def test_approve_then_public(client, session):
    h = auth_headers(await make_admin(session))
    _, _, _, zamana = await _world(session)
    promo = await make_promotion(session, zamana, status="pending")
    r = await client.get("/api/v1/admin/promotions", params={"status": "pending"}, headers=h)
    assert [p["id"] for p in r.json()["items"]] == [promo.id]
    r = await client.post(f"/api/v1/admin/promotions/{promo.id}/approve", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert len((await client.get("/api/v1/promotions")).json()["items"]) == 1
    r = await client.post(f"/api/v1/admin/promotions/{promo.id}/approve", headers=h)
    assert r.status_code == 409


async def test_reject_with_comment(client, session):
    h = auth_headers(await make_admin(session))
    _, _, _, zamana = await _world(session)
    promo = await make_promotion(session, zamana, status="pending")
    r = await client.post(
        f"/api/v1/admin/promotions/{promo.id}/reject", json={"comment": "нет фото"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "нет фото"


async def test_admin_update_and_delete(client, session):
    h = auth_headers(await make_admin(session))
    _, _, _, zamana = await _world(session)
    promo = await make_promotion(session, zamana)
    r = await client.patch(f"/api/v1/admin/promotions/{promo.id}", json={"badge": "2+1"}, headers=h)
    assert r.status_code == 200
    assert r.json()["badge"] == "2+1"
    r = await client.patch(f"/api/v1/admin/promotions/{promo.id}", json={"shop_id": 1}, headers=h)
    assert r.status_code == 422
    assert (
        await client.delete(f"/api/v1/admin/promotions/{promo.id}", headers=h)
    ).status_code == 204
