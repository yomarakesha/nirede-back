"""A shop with several locations shows up wherever it has one."""

from sqlalchemy import insert, select

from app.modules.notifications.models import Notification
from app.modules.notifications.service import notify_promotion_published
from app.modules.users.models import user_malls
from tests.factories import (
    add_location,
    make_city,
    make_mall,
    make_promotion,
    make_shop,
    make_user,
    make_women_tree,
)


async def _chain(session):
    """Moda Line: Беркарар floor 2, Аркач floor 1, and a street address in Мары."""
    city = await make_city(session)
    other = await make_city(session, "Мары", "Mary")
    berkarar = await make_mall(session, city, "Беркарар")
    arkach = await make_mall(session, city, "Аркач")
    _, _, coat = await make_women_tree(session)
    shop = await make_shop(
        session, "Moda Line", mall=berkarar, floor=2, number="214", categories=[coat]
    )
    await add_location(session, shop, mall=arkach, floor=1, number="24")
    await add_location(session, shop, city=other)
    return shop, city, other, berkarar, arkach, coat


async def test_mall_shops_lists_only_that_malls_locations(client, session):
    shop, _, _, berkarar, arkach, _ = await _chain(session)
    for mall, number in ((berkarar, "214"), (arkach, "24")):
        r = await client.get(f"/api/v1/malls/{mall.id}/shops")
        [item] = r.json()["items"]
        assert item["id"] == shop.id
        assert [loc["number"] for loc in item["locations"]] == [number]


async def test_mall_shops_floor_filter_uses_location_in_that_mall(client, session):
    _, _, _, berkarar, arkach, _ = await _chain(session)
    # Floor 1 is the Аркач location, not the Беркарар one.
    r = await client.get(f"/api/v1/malls/{berkarar.id}/shops", params={"floor": 1})
    assert r.json()["total"] == 0
    r = await client.get(f"/api/v1/malls/{arkach.id}/shops", params={"floor": 1})
    assert r.json()["total"] == 1


async def test_mall_detail_counts_shop_in_each_mall(client, session):
    _, _, _, berkarar, arkach, _ = await _chain(session)
    for mall in (berkarar, arkach):
        assert (await client.get(f"/api/v1/malls/{mall.id}")).json()["shop_count"] == 1


async def test_search_lists_shop_in_every_group(client, session):
    shop, _, _, berkarar, arkach, coat = await _chain(session)
    r = await client.get("/api/v1/search", params={"category_id": coat.id})
    body = r.json()
    assert body["total_shops"] == 1
    assert body["total_malls"] == 2
    groups = {g["mall"]["id"] if g["mall"] else None: g for g in body["groups"]}
    assert set(groups) == {berkarar.id, arkach.id, None}
    assert body["groups"][-1]["mall"] is None
    for key, number in ((berkarar.id, "214"), (arkach.id, "24")):
        [item] = groups[key]["shops"]
        assert [loc["number"] for loc in item["locations"]] == [number]
    [standalone] = groups[None]["shops"]
    assert [loc["mall"] for loc in standalone["locations"]] == [None]


async def test_search_city_filter_keeps_locations_in_that_city(client, session):
    _, _, other, _, _, coat = await _chain(session)
    r = await client.get("/api/v1/search", params={"category_id": coat.id, "city_id": other.id})
    body = r.json()
    assert body["total_shops"] == 1
    assert [g["mall"] for g in body["groups"]] == [None]


async def test_suggest_counts_shop_per_mall(client, session):
    _, _, _, berkarar, arkach, _ = await _chain(session)
    r = await client.get("/api/v1/search/suggest", params={"q": "пальто"})
    malls = r.json()["malls_for_top_category"]
    assert sorted(m["mall_id"] for m in malls) == sorted([berkarar.id, arkach.id])
    assert all(m["shop_count"] == 1 for m in malls)


async def test_promotion_feed_mall_filter(client, session):
    shop, city, other, _, arkach, _ = await _chain(session)
    await make_promotion(session, shop)
    for params in ({"mall_id": arkach.id}, {"city_id": other.id}, {"city_id": city.id}):
        r = await client.get("/api/v1/promotions", params=params)
        items = r.json()["items"]
        assert [p["shop"]["id"] for p in items] == [shop.id], params


async def test_promotion_reaches_followers_of_every_mall(session):
    shop, _, _, berkarar, arkach, _ = await _chain(session)
    u1 = await make_user(session, phone="+99365000001")
    u2 = await make_user(session, phone="+99365000002")
    await session.execute(insert(user_malls).values(user_id=u1.id, mall_id=berkarar.id))
    await session.execute(insert(user_malls).values(user_id=u2.id, mall_id=arkach.id))
    promo = await make_promotion(session, shop)
    sent = await notify_promotion_published(session, promo)
    assert sorted(n.user_id for n in sent) == sorted([u1.id, u2.id])
    n = await session.scalar(select(Notification).where(Notification.user_id == u1.id))
    assert n.title_ru == "Moda Line"
