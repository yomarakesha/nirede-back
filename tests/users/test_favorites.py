from tests.factories import auth_headers, make_city, make_mall, make_shop, make_user


async def _world(session):
    user = await make_user(session)
    city = await make_city(session)
    mall = await make_mall(session, city)
    a = await make_shop(session, "Moda Line", mall=mall, floor=2, number="214")
    b = await make_shop(session, "Ýüpek", city=city)
    return auth_headers(user), mall, a, b


async def test_add_list_remove_favorite(client, session):
    h, _, a, b = await _world(session)
    assert (await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)).status_code == 204
    assert (await client.put(f"/api/v1/me/favorites/{b.id}", headers=h)).status_code == 204
    r = await client.get("/api/v1/me/favorites", headers=h)
    assert sorted(s["name"] for s in r.json()) == ["Moda Line", "Ýüpek"]
    assert (await client.delete(f"/api/v1/me/favorites/{a.id}", headers=h)).status_code == 204
    r = await client.get("/api/v1/me/favorites", headers=h)
    assert [s["name"] for s in r.json()] == ["Ýüpek"]


async def test_put_twice_idempotent(client, session):
    h, _, a, _ = await _world(session)
    await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)
    r = await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)
    assert r.status_code == 204
    assert len((await client.get("/api/v1/me/favorites", headers=h)).json()) == 1
    assert (await client.delete(f"/api/v1/me/favorites/{a.id}", headers=h)).status_code == 204
    assert (await client.delete(f"/api/v1/me/favorites/{a.id}", headers=h)).status_code == 204


async def test_unknown_or_inactive_shop_404(client, session):
    h, _, a, _ = await _world(session)
    assert (await client.put("/api/v1/me/favorites/999999", headers=h)).status_code == 404
    a.is_active = False
    await session.flush()
    assert (await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)).status_code == 404


async def test_inactive_favorite_hidden_from_list(client, session):
    h, _, a, _ = await _world(session)
    await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)
    a.is_active = False
    await session.flush()
    assert (await client.get("/api/v1/me/favorites", headers=h)).json() == []


async def test_is_saved_flag(client, session):
    h, mall, a, _ = await _world(session)
    assert (await client.get(f"/api/v1/shops/{a.id}")).json()["is_saved"] is False
    assert (await client.get(f"/api/v1/shops/{a.id}", headers=h)).json()["is_saved"] is False
    await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)
    assert (await client.get(f"/api/v1/shops/{a.id}", headers=h)).json()["is_saved"] is True
    assert (await client.get(f"/api/v1/malls/{mall.id}", headers=h)).json()["is_saved"] is False
    await client.put(f"/api/v1/me/malls/{mall.id}", headers=h)
    assert (await client.get(f"/api/v1/malls/{mall.id}", headers=h)).json()["is_saved"] is True


async def test_my_malls_roundtrip(client, session):
    h, mall, _, _ = await _world(session)
    assert (await client.put(f"/api/v1/me/malls/{mall.id}", headers=h)).status_code == 204
    r = await client.get("/api/v1/me/malls", headers=h)
    assert [m["name_ru"] for m in r.json()] == ["Беркарар"]
    assert (await client.delete(f"/api/v1/me/malls/{mall.id}", headers=h)).status_code == 204
    assert (await client.get("/api/v1/me/malls", headers=h)).json() == []
    assert (await client.put("/api/v1/me/malls/999999", headers=h)).status_code == 404


async def test_favorites_are_per_user(client, session):
    h, _, a, _ = await _world(session)
    other = auth_headers(await make_user(session, phone="+99365000001"))
    await client.put(f"/api/v1/me/favorites/{a.id}", headers=h)
    assert (await client.get("/api/v1/me/favorites", headers=other)).json() == []


async def test_requires_auth(client):
    assert (await client.get("/api/v1/me/favorites")).status_code == 401
    assert (await client.put("/api/v1/me/malls/1")).status_code == 401
