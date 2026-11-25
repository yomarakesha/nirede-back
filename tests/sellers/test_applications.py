from sqlalchemy import select

from app.modules.shops.models import Shop
from tests.factories import auth_headers, make_admin, make_city, make_mall, make_shop, make_user


async def _world(session):
    admin = await make_admin(session)
    user = await make_user(session)
    city = await make_city(session)
    mall = await make_mall(session, city)
    return auth_headers(admin), user, auth_headers(user), city, mall


APP = {
    "shop_name": "Moda Line",
    "floor": 2,
    "number": "214",
    "contact_phone": "+993 65 12 34 56",
}


async def test_claim_existing_shop_flow(client, session):
    ah, user, uh, city, mall = await _world(session)
    shop = await make_shop(session, "Moda Line", mall=mall, floor=2, number="214")
    r = await client.post(
        "/api/v1/me/seller-applications",
        json={**APP, "shop_id": shop.id, "mall_id": mall.id},
        headers=uh,
    )
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert r.json()["contact_phone"] == "+99365123456"

    r = await client.get(
        "/api/v1/admin/seller-applications", params={"status": "pending"}, headers=ah
    )
    assert [a["id"] for a in r.json()["items"]] == [app_id]

    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve",
        json={"subscription": {"amount": "30", "days": 30}},
        headers=ah,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["shop_id"] == shop.id

    me = (await client.get("/api/v1/me", headers=uh)).json()
    assert me["role"] == "seller"
    assert (await client.get(f"/api/v1/shops/{shop.id}")).json()["is_premium"] is True
    mine = (await client.get("/api/v1/seller/shops", headers=uh)).json()
    assert [s["name"] for s in mine] == ["Moda Line"]
    assert mine[0]["subscription_ends_at"] is not None


async def test_new_shop_flow_requires_shop_data(client, session):
    ah, user, uh, city, mall = await _world(session)
    r = await client.post(
        "/api/v1/me/seller-applications", json={**APP, "mall_id": mall.id}, headers=uh
    )
    app_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json={}, headers=ah
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "shop_data_required"
    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve",
        json={
            "shop": {
                "name": "Moda Line",
                "locations": [{"mall_id": mall.id, "floor": 2, "number": "214"}],
            }
        },
        headers=ah,
    )
    assert r.status_code == 200, r.text
    shop_id = r.json()["shop_id"]
    shop = (await client.get(f"/api/v1/admin/shops/{shop_id}", headers=ah)).json()
    assert shop["owner_id"] == user.id
    assert shop["is_premium"] is False


async def test_one_pending_application(client, session):
    _, _, uh, _, mall = await _world(session)
    body = {**APP, "mall_id": mall.id}
    assert (
        await client.post("/api/v1/me/seller-applications", json=body, headers=uh)
    ).status_code == 201
    r = await client.post("/api/v1/me/seller-applications", json=body, headers=uh)
    assert r.status_code == 409
    assert r.json()["detail"] == "application_pending"


async def test_unknown_shop_in_application_404(client, session):
    _, _, uh, _, _ = await _world(session)
    r = await client.post(
        "/api/v1/me/seller-applications", json={**APP, "shop_id": 999999}, headers=uh
    )
    assert r.status_code == 404


async def test_shop_already_owned_conflict(client, session):
    ah, _, uh, _, mall = await _world(session)
    owner = await make_user(session, phone="+99365000077", role="seller")
    shop = await make_shop(session, "Moda Line", mall=mall, floor=2, owner_id=owner.id)
    r = await client.post(
        "/api/v1/me/seller-applications", json={**APP, "shop_id": shop.id}, headers=uh
    )
    app_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json={}, headers=ah
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "shop_already_owned"


async def test_reject_sets_comment(client, session):
    ah, _, uh, _, mall = await _world(session)
    r = await client.post(
        "/api/v1/me/seller-applications", json={**APP, "mall_id": mall.id}, headers=uh
    )
    app_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/reject",
        json={"comment": "не дозвонились"},
        headers=ah,
    )
    assert r.status_code == 200
    mine = (await client.get("/api/v1/me/seller-applications", headers=uh)).json()
    assert mine[0]["status"] == "rejected"
    assert mine[0]["admin_comment"] == "не дозвонились"
    r = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json={}, headers=ah
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "already_reviewed"


async def test_seller_shops_lists_only_own(client, session):
    _, _, _, city, mall = await _world(session)
    seller = await make_user(session, phone="+99365000011", role="seller")
    await make_shop(session, "Mine", mall=mall, floor=1, owner_id=seller.id)
    await make_shop(session, "Not mine", mall=mall, floor=1)
    r = await client.get("/api/v1/seller/shops", headers=auth_headers(seller))
    assert [s["name"] for s in r.json()] == ["Mine"]
    assert r.json()[0]["pending_change_requests"] == 0


async def test_plain_user_cannot_list_seller_shops(client, session):
    _, _, uh, _, _ = await _world(session)
    assert (await client.get("/api/v1/seller/shops", headers=uh)).status_code == 403


async def test_admin_change_user_role(client, session):
    ah, user, _, _, _ = await _world(session)
    r = await client.get("/api/v1/admin/users", params={"q": "6512"}, headers=ah)
    assert [u["id"] for u in r.json()["items"]] == [user.id]
    r = await client.patch(f"/api/v1/admin/users/{user.id}", json={"role": "seller"}, headers=ah)
    assert r.status_code == 200
    assert r.json()["role"] == "seller"
    r = await client.get("/api/v1/admin/users", params={"role": "seller"}, headers=ah)
    assert r.json()["total"] == 1


async def test_admin_cannot_demote_self(client, session):
    admin = await make_admin(session)
    r = await client.patch(
        f"/api/v1/admin/users/{admin.id}", json={"role": "user"}, headers=auth_headers(admin)
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "cannot_demote_self"


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
    body = {"shop": {"name": "S", "locations": [{"mall_id": mall.id, "floor": 1, "number": "1"}]}}
    first = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json=body, headers=h
    )
    second = await client.post(
        f"/api/v1/admin/seller-applications/{app_id}/approve", json=body, headers=h
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert len(list(await session.scalars(select(Shop)))) == 1
