from tests.factories import auth_headers, make_admin, make_city, make_user

CITY = {"name_ru": "Ашхабад", "name_tk": "Aşgabat"}


async def test_admin_crud_city(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post("/api/v1/admin/cities", json=CITY, headers=h)
    assert r.status_code == 201, r.text
    city_id = r.json()["id"]
    assert r.json()["is_active"] is True

    r = await client.patch(
        f"/api/v1/admin/cities/{city_id}", json={"name_tk": "Ashgabat"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["name_tk"] == "Ashgabat"
    assert r.json()["name_ru"] == "Ашхабад"

    r = await client.get("/api/v1/admin/cities", headers=h)
    assert r.json()["total"] == 1

    r = await client.get(f"/api/v1/admin/cities/{city_id}", headers=h)
    assert r.status_code == 200

    r = await client.delete(f"/api/v1/admin/cities/{city_id}", headers=h)
    assert r.status_code == 204
    r = await client.get(f"/api/v1/admin/cities/{city_id}", headers=h)
    assert r.status_code == 404


async def test_public_lists_only_active(client, session):
    h = auth_headers(await make_admin(session))
    await client.post("/api/v1/admin/cities", json=CITY, headers=h)
    await client.post(
        "/api/v1/admin/cities",
        json={"name_ru": "Мары", "name_tk": "Mary", "is_active": False},
        headers=h,
    )
    r = await client.get("/api/v1/cities")
    assert r.status_code == 200
    assert [c["name_ru"] for c in r.json()] == ["Ашхабад"]


async def test_non_admin_forbidden(client, session):
    user = await make_user(session)
    r = await client.post("/api/v1/admin/cities", json=CITY, headers=auth_headers(user))
    assert r.status_code == 403
    r = await client.post("/api/v1/admin/cities", json=CITY)
    assert r.status_code == 401


async def test_validation_empty_name(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post("/api/v1/admin/cities", json={"name_ru": "", "name_tk": "x"}, headers=h)
    assert r.status_code == 422


async def test_admin_patch_city_null_422(client, session):
    h = auth_headers(await make_admin(session))
    city = await make_city(session)
    r = await client.patch(f"/api/v1/admin/cities/{city.id}", json={"name_ru": None}, headers=h)
    assert r.status_code == 422
