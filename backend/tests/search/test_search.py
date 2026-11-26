async def _search(client, **params):
    r = await client.get("/api/v1/search", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_search_groups(client, world):
    body = await _search(client, category_id=world.w_coat.id)
    assert body["category"]["id"] == world.w_coat.id
    assert body["total_shops"] == 7
    assert body["total_malls"] == 3
    groups = body["groups"]
    assert groups[0]["mall"]["name_ru"] == "Беркарар"
    assert groups[0]["shop_count"] == 4
    assert [s["name"] for s in groups[0]["shops"]] == [
        "Lady Style",
        "Moda Line",
        "Elegant",
        "Palto House",
    ]
    assert groups[-1]["mall"] is None
    assert [s["name"] for s in groups[-1]["shops"]] == ["Город Пальто"]
    assert body["similar_categories"] == []


async def test_search_parent_category_covers_subtree(client, world):
    body = await _search(client, category_id=world.women.id)
    assert body["total_shops"] == 7


async def test_search_by_q_uses_top_category(client, world):
    body = await _search(client, q="женское пальто")
    assert body["category"]["id"] == world.w_coat.id
    assert body["total_shops"] == 7


async def test_search_mall_filter(client, world):
    body = await _search(client, category_id=world.w_coat.id, mall_id=world.arkach.id)
    assert [g["mall"]["name_ru"] for g in body["groups"]] == ["Аркач"]
    assert body["total_shops"] == 1


async def test_search_city_filter(client, world, session):
    from tests.factories import make_city

    other = await make_city(session, "Мары", "Mary")
    body = await _search(client, category_id=world.w_coat.id, city_id=other.id)
    assert body["total_shops"] == 0


async def test_empty_result_similar_categories(client, world):
    body = await _search(client, q="детская норковая шуба")
    assert body["total_shops"] == 0
    assert body["groups"] == []
    names = [c["name_ru"] for c in body["similar_categories"]]
    assert "Шубы" in names
    assert "Верхняя одежда" in names


async def test_category_without_shops_gives_similar(client, world):
    body = await _search(client, category_id=world.k_fur.id)
    assert body["total_shops"] == 0
    assert body["category"]["id"] == world.k_fur.id
    assert world.k_outer.id in [c["id"] for c in body["similar_categories"]]


async def test_inactive_shop_hidden(client, world):
    body = await _search(client, category_id=world.w_coat.id)
    names = [s["name"] for g in body["groups"] for s in g["shops"]]
    assert "Hidden" not in names


async def test_requires_exactly_one_of_category_or_q(client, world):
    assert (await client.get("/api/v1/search")).status_code == 422
    r = await client.get("/api/v1/search", params={"q": "пальто", "category_id": world.w_coat.id})
    assert r.status_code == 422


async def test_unknown_category_404(client, world):
    assert (await client.get("/api/v1/search", params={"category_id": 999999})).status_code == 404
