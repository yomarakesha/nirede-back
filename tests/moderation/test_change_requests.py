from datetime import timedelta

from sqlalchemy import update

from app.modules.shops.models import Subscription
from app.timeutil import utcnow
from tests.factories import auth_headers, make_shop, make_user


async def _submit(client, w, payload, shop_id=None, headers=None):
    return await client.post(
        f"/api/v1/seller/shops/{shop_id or w.shop.id}/change-requests",
        json=payload,
        headers=headers or w.sh,
    )


async def _how_to_find(client, shop_id):
    return (await client.get(f"/api/v1/shops/{shop_id}")).json()["how_to_find_ru"]


async def test_submit_and_approve_applies(client, seller_world):
    w = seller_world
    r = await _submit(client, w, {"how_to_find_ru": "Новый текст"})
    assert r.status_code == 201, r.text
    cr = r.json()
    assert cr["status"] == "pending"
    assert cr["payload"] == {"how_to_find_ru": "Новый текст"}
    assert await _how_to_find(client, w.shop.id) == "Старый текст"

    queue = (
        await client.get(
            "/api/v1/admin/change-requests", params={"status": "pending"}, headers=w.ah
        )
    ).json()
    assert queue["total"] == 1
    assert queue["items"][0]["current"]["how_to_find_ru"] == "Старый текст"

    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert await _how_to_find(client, w.shop.id) == "Новый текст"


async def test_approve_categories_and_photos(client, seller_world, session):
    from tests.factories import make_women_tree

    w = seller_world
    _, _, coat = await make_women_tree(session)
    r = await _submit(client, w, {"category_ids": [coat.id], "photos": ["new.webp"]})
    await client.post(f"/api/v1/admin/change-requests/{r.json()['id']}/approve", headers=w.ah)
    shop = (await client.get(f"/api/v1/shops/{w.shop.id}")).json()
    assert [c["name_ru"] for c in shop["categories"]] == ["Пальто"]
    assert [p["path"] for p in shop["photos"]] == ["new.webp"]


async def test_reject_leaves_shop(client, seller_world):
    w = seller_world
    cr = (await _submit(client, w, {"how_to_find_ru": "Новый"})).json()
    r = await client.post(
        f"/api/v1/admin/change-requests/{cr['id']}/reject",
        json={"comment": "опечатка"},
        headers=w.ah,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "опечатка"
    assert await _how_to_find(client, w.shop.id) == "Старый текст"
    mine = (await client.get("/api/v1/seller/change-requests", headers=w.sh)).json()
    assert mine[0]["admin_comment"] == "опечатка"


async def test_not_owner_403(client, seller_world, session):
    w = seller_world
    other = await make_user(session, phone="+99365000012", role="seller")
    r = await _submit(client, w, {"name": "X"}, headers=auth_headers(other))
    assert r.status_code == 403
    assert r.json()["detail"] == "not_owner"


async def test_no_subscription_403(client, seller_world, session):
    w = seller_world
    other_shop = await make_shop(session, "Free", mall=w.mall, floor=1, owner_id=w.seller.id)
    r = await _submit(client, w, {"name": "X"}, shop_id=other_shop.id)
    assert r.status_code == 403
    assert r.json()["detail"] == "subscription_required"


async def test_invalid_payload_422(client, seller_world):
    r = await _submit(client, seller_world, {"opens_at": "25:99"})
    assert r.status_code == 422


async def test_empty_payload_422(client, seller_world):
    r = await _submit(client, seller_world, {})
    assert r.status_code == 422
    assert r.json()["detail"] == "empty_change"


async def test_seller_cannot_change_location(client, seller_world):
    r = await _submit(client, seller_world, {"mall_id": 2})
    assert r.status_code == 422
    r = await _submit(client, seller_world, {"is_active": False})
    assert r.status_code == 422


async def test_resubmit_replaces_pending(client, seller_world):
    w = seller_world
    first = (await _submit(client, w, {"how_to_find_ru": "A"})).json()
    second = (await _submit(client, w, {"how_to_find_ru": "B"})).json()
    assert second["id"] == first["id"]
    assert second["payload"] == {"how_to_find_ru": "B"}
    queue = (await client.get("/api/v1/admin/change-requests", headers=w.ah)).json()
    assert queue["total"] == 1
    shops = (await client.get("/api/v1/seller/shops", headers=w.sh)).json()
    assert shops[0]["pending_change_requests"] == 1


async def test_approve_after_subscription_expired_autorejects(client, seller_world, session):
    w = seller_world
    cr = (await _submit(client, w, {"how_to_find_ru": "Новый"})).json()
    await session.execute(update(Subscription).values(ends_at=utcnow() - timedelta(seconds=1)))
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "subscription_expired"
    shop = (await client.get(f"/api/v1/admin/shops/{w.shop.id}", headers=w.ah)).json()
    assert shop["how_to_find_ru"] == "Старый текст"


async def test_approve_after_shop_deleted_autorejects(client, seller_world):
    w = seller_world
    cr = (await _submit(client, w, {"how_to_find_ru": "Новый"})).json()
    assert (
        await client.delete(f"/api/v1/admin/shops/{w.shop.id}", headers=w.ah)
    ).status_code == 204
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "entity_deleted"


async def test_approve_after_category_deleted_autorejects(client, seller_world, session):
    from tests.factories import make_category

    w = seller_world
    cat = await make_category(session, "Временная")
    cr = (await _submit(client, w, {"category_ids": [cat.id]})).json()
    assert (
        await client.delete(f"/api/v1/admin/categories/{cat.id}", headers=w.ah)
    ).status_code == 204
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["admin_comment"] == "unknown_category"


async def test_double_review_409(client, seller_world):
    w = seller_world
    cr = (await _submit(client, w, {"name": "Moda Line 2"})).json()
    await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    r = await client.post(f"/api/v1/admin/change-requests/{cr['id']}/approve", headers=w.ah)
    assert r.status_code == 409
    assert r.json()["detail"] == "already_reviewed"
