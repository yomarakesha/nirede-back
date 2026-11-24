from tests.factories import auth_headers, make_admin, make_city, make_mall, make_shop


def _mall_body(city_id, **kw):
    body = {
        "city_id": city_id,
        "name_ru": "Беркарар",
        "name_tk": "Berkarar",
        "address_ru": "ул. Ататюрка, 80",
        "address_tk": "Atatürk köçesi, 80",
        "phone": "+99312000000",
        "opens_at": "09:00",
        "closes_at": "23:00",
        "layout": "floors",
        "floors_count": 4,
    }
    return {**body, **kw}


async def test_admin_crud_mall(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    r = await client.post("/api/v1/admin/malls", json=_mall_body(city.id), headers=h)
    assert r.status_code == 201, r.text
    mall_id = r.json()["id"]

    r = await client.patch(f"/api/v1/admin/malls/{mall_id}", json={"closes_at": "22:00"}, headers=h)
    assert r.status_code == 200
    assert r.json()["closes_at"] == "22:00:00"

    r = await client.get("/api/v1/admin/malls", headers=h)
    assert r.json()["total"] == 1

    assert (await client.delete(f"/api/v1/admin/malls/{mall_id}", headers=h)).status_code == 204
    assert (await client.get(f"/api/v1/malls/{mall_id}")).status_code == 404


async def test_floors_layout_requires_floors_count(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    r = await client.post(
        "/api/v1/admin/malls", json=_mall_body(city.id, floors_count=None), headers=h
    )
    assert r.status_code == 422


async def test_rows_layout_without_floors_count(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    r = await client.post(
        "/api/v1/admin/malls",
        json=_mall_body(city.id, name_ru="Толкучка", layout="rows", floors_count=None),
        headers=h,
    )
    assert r.status_code == 201, r.text


async def test_unknown_city_404(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post("/api/v1/admin/malls", json=_mall_body(999999), headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "city_not_found"


async def test_replace_photos_keeps_order(client, session):
    h = auth_headers(await make_admin(session))
    mall = await make_mall(session, await make_city(session))
    url = f"/api/v1/admin/malls/{mall.id}/photos"
    r = await client.put(url, json={"paths": ["a.webp", "b.webp", "c.webp"]}, headers=h)
    assert r.status_code == 200, r.text
    r = await client.put(url, json={"paths": ["c.webp", "a.webp"]}, headers=h)
    r = await client.get(f"/api/v1/malls/{mall.id}")
    assert [p["path"] for p in r.json()["photos"]] == ["c.webp", "a.webp"]
    assert r.json()["photos"][0]["url"] == "/media/c.webp"


async def test_public_detail(client, session):
    h = auth_headers(await make_admin(session))
    mall = await make_mall(session, await make_city(session), opens_at=None, closes_at=None)
    floors = [
        {"number": 2, "summary_ru": "Одежда, сумки", "summary_tk": "Eşikler"},
        {"number": 1, "summary_ru": "Супермаркет", "summary_tk": "Supermarket"},
    ]
    r = await client.put(f"/api/v1/admin/malls/{mall.id}/floors", json=floors, headers=h)
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/v1/malls/{mall.id}")
    assert r.status_code == 200
    body = r.json()
    assert [f["number"] for f in body["floors"]] == [1, 2]
    assert body["is_open_now"] is False
    assert body["shop_count"] == 0


async def test_duplicate_floor_numbers_422(client, session):
    h = auth_headers(await make_admin(session))
    mall = await make_mall(session, await make_city(session))
    floors = [
        {"number": 1, "summary_ru": "a", "summary_tk": "a"},
        {"number": 1, "summary_ru": "b", "summary_tk": "b"},
    ]
    r = await client.put(f"/api/v1/admin/malls/{mall.id}/floors", json=floors, headers=h)
    assert r.status_code == 422


async def test_filter_by_city_and_inactive_hidden(client, session):
    a = await make_city(session)
    b = await make_city(session, "Мары", "Mary")
    await make_mall(session, a, "Беркарар")
    await make_mall(session, b, "Мары Молл")
    await make_mall(session, a, "Закрытый", is_active=False)
    r = await client.get("/api/v1/malls", params={"city_id": a.id})
    assert [m["name_ru"] for m in r.json()] == ["Беркарар"]
    r = await client.get("/api/v1/malls")
    assert len(r.json()) == 2


async def test_delete_city_with_mall_conflict(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    await make_mall(session, city)
    r = await client.delete(f"/api/v1/admin/cities/{city.id}", headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "city_in_use"


async def test_mall_in_inactive_city_hidden(client, session):
    city = await make_city(session)
    mall = await make_mall(session, city)
    city.is_active = False
    await session.flush()
    assert (await client.get("/api/v1/malls")).json() == []
    assert (await client.get(f"/api/v1/malls/{mall.id}")).status_code == 404


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


async def test_layout_check_matches_shop_validation(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    floors = await make_mall(session, city, floors_count=4)
    await make_shop(session, "X", mall=floors, floor=0)
    r = await client.patch(f"/api/v1/admin/malls/{floors.id}", json={"sort_order": 1}, headers=h)
    assert r.status_code == 409
    rows = await make_mall(session, city, "Rows", layout="rows")
    await make_shop(session, "Y", mall=rows, row="")
    r = await client.patch(f"/api/v1/admin/malls/{rows.id}", json={"sort_order": 1}, headers=h)
    assert r.status_code == 409
