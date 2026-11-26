from tests.factories import make_category, make_city, make_mall, make_shop, make_women_tree


async def test_mall_shops_premium_first(client, session):
    mall = await make_mall(session, await make_city(session))
    await make_shop(session, "Elegant", mall=mall, floor=2, number="216")
    await make_shop(session, "Moda Line", mall=mall, floor=2, number="214", premium=True)
    await make_shop(session, "Lady Style", mall=mall, floor=2, number="217", premium=True)
    await make_shop(session, "First Floor", mall=mall, floor=1, number="1")
    r = await client.get(f"/api/v1/malls/{mall.id}/shops", params={"floor": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert [s["name"] for s in body["items"]] == ["Lady Style", "Moda Line", "Elegant"]
    assert [s["is_premium"] for s in body["items"]] == [True, True, False]


async def test_mall_shops_by_row(client, session):
    market = await make_mall(session, await make_city(session), "Толкучка", layout="rows")
    await make_shop(session, "Ýüpek", mall=market, row="14", number="32")
    await make_shop(session, "Gülälek", mall=market, row="15", number="3")
    r = await client.get(f"/api/v1/malls/{market.id}/shops", params={"row": "14"})
    assert [s["name"] for s in r.json()["items"]] == ["Ýüpek"]


async def test_mall_shops_category_subtree(client, session):
    mall = await make_mall(session, await make_city(session))
    root, _, coat = await make_women_tree(session)
    men = await make_category(session, "Мужчинам")
    await make_shop(session, "Moda Line", mall=mall, floor=2, categories=[coat])
    await make_shop(session, "Men Only", mall=mall, floor=2, categories=[men])
    r = await client.get(f"/api/v1/malls/{mall.id}/shops", params={"category_id": root.id})
    assert [s["name"] for s in r.json()["items"]] == ["Moda Line"]
    assert r.json()["items"][0]["categories"][0]["name_ru"] == "Пальто"


async def test_mall_detail_counts(client, session):
    mall = await make_mall(session, await make_city(session))
    root, _, coat = await make_women_tree(session)
    men = await make_category(session, "Мужчинам")
    await make_shop(session, "A", mall=mall, floor=1, categories=[coat])
    await make_shop(session, "B", mall=mall, floor=1, categories=[men, coat])
    await make_shop(session, "Hidden", mall=mall, floor=1, is_active=False)
    body = (await client.get(f"/api/v1/malls/{mall.id}")).json()
    assert body["shop_count"] == 2
    assert sorted(c["name_ru"] for c in body["root_categories"]) == ["Женщинам", "Мужчинам"]
