from app.modules.categories.service import ancestors_map, subtree_ids
from tests.factories import auth_headers, make_admin, make_category, make_women_tree


async def test_subtree_ids(session):
    root, outer, coat = await make_women_tree(session)
    await make_category(session, "Мужчинам")
    assert sorted(await subtree_ids(session, root.id)) == sorted([root.id, outer.id, coat.id])
    assert await subtree_ids(session, coat.id) == [coat.id]


async def test_ancestors_map(session):
    root, outer, coat = await make_women_tree(session)
    paths = await ancestors_map(session, [coat.id, root.id])
    assert [c.name_ru for c in paths[coat.id]] == ["Женщинам", "Верхняя одежда", "Пальто"]
    assert [c.name_ru for c in paths[root.id]] == ["Женщинам"]


async def test_public_roots(client, session):
    await make_women_tree(session)
    await make_category(session, "Скрытая", is_active=False)
    r = await client.get("/api/v1/categories")
    assert [c["name_ru"] for c in r.json()] == ["Женщинам"]


async def test_detail_two_levels(client, session):
    root, outer, coat = await make_women_tree(session)
    await make_category(session, "Пуховики", outer)
    await make_category(session, "Подкатегория пальто", coat)
    r = await client.get(f"/api/v1/categories/{root.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["name_ru"] == "Женщинам"
    [child] = body["children"]
    assert child["name_ru"] == "Верхняя одежда"
    assert sorted(c["name_ru"] for c in child["children"]) == ["Пальто", "Пуховики"]
    assert all(c["children"] == [] for c in child["children"])


async def test_tree(client, session):
    await make_women_tree(session)
    r = await client.get("/api/v1/categories/tree")
    [root] = r.json()
    assert root["children"][0]["children"][0]["name_ru"] == "Пальто"


async def test_inactive_hidden_publicly(client, session):
    root, outer, coat = await make_women_tree(session)
    outer.is_active = False
    await session.flush()
    r = await client.get(f"/api/v1/categories/{root.id}")
    assert r.json()["children"] == []
    assert (await client.get(f"/api/v1/categories/{outer.id}")).status_code == 404


async def test_admin_create_and_update(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post(
        "/api/v1/admin/categories",
        json={"name_ru": "Женщинам", "name_tk": "Aýallara", "slug": "women"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    root_id = r.json()["id"]
    r = await client.post(
        "/api/v1/admin/categories",
        json={"name_ru": "Пальто", "name_tk": "Palto", "slug": "women-coats", "parent_id": root_id},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["parent_id"] == root_id
    r = await client.post(
        "/api/v1/admin/categories",
        json={"name_ru": "x", "name_tk": "x", "slug": "women"},
        headers=h,
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "slug_taken"


async def test_unknown_parent_404(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post(
        "/api/v1/admin/categories",
        json={"name_ru": "x", "name_tk": "x", "slug": "x", "parent_id": 999999},
        headers=h,
    )
    assert r.status_code == 404


async def test_cycle_rejected(client, session):
    h = auth_headers(await make_admin(session))
    root, outer, coat = await make_women_tree(session)
    r = await client.patch(
        f"/api/v1/admin/categories/{root.id}", json={"parent_id": coat.id}, headers=h
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "category_cycle"
    r = await client.patch(
        f"/api/v1/admin/categories/{root.id}", json={"parent_id": root.id}, headers=h
    )
    assert r.status_code == 422


async def test_move_to_root(client, session):
    h = auth_headers(await make_admin(session))
    root, outer, coat = await make_women_tree(session)
    r = await client.patch(
        f"/api/v1/admin/categories/{coat.id}", json={"parent_id": None}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["parent_id"] is None


async def test_delete_with_children_conflict(client, session):
    h = auth_headers(await make_admin(session))
    root, outer, coat = await make_women_tree(session)
    r = await client.delete(f"/api/v1/admin/categories/{root.id}", headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == "category_in_use"
    r = await client.delete(f"/api/v1/admin/categories/{coat.id}", headers=h)
    assert r.status_code == 204
