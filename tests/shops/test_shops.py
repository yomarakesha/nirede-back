from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.shops.models import ShopLocation, Subscription
from app.timeutil import utcnow
from tests.factories import (
    add_location,
    auth_headers,
    make_admin,
    make_city,
    make_mall,
    make_shop,
    make_women_tree,
)


async def _setup(session):
    admin = await make_admin(session)
    city = await make_city(session)
    other = await make_city(session, "Мары", "Mary")
    mall = await make_mall(session, city)
    rows = await make_mall(session, city, "Толкучка", layout="rows")
    _, _, coat = await make_women_tree(session)
    return auth_headers(admin), city, other, mall, rows, coat


def _in_mall(mall, **kw) -> dict:
    return {"mall_id": mall.id, "floor": 1, "number": "1", **kw}


async def test_create_in_mall_shop_sets_city(client, session):
    h, city, other, mall, _, coat = await _setup(session)
    body = {
        "name": "Moda Line",
        "locations": [_in_mall(mall, city_id=other.id, floor=2, number="214")],
        "category_ids": [coat.id],
        "photos": ["a.webp", "b.webp"],
        "how_to_find_ru": "Налево до № 214",
    }
    r = await client.post("/api/v1/admin/shops", json=body, headers=h)
    assert r.status_code == 201, r.text
    data = r.json()
    [loc] = data["locations"]
    assert loc["city_id"] == city.id
    assert loc["mall"]["id"] == mall.id
    assert (loc["floor"], loc["number"]) == (2, "214")
    assert [c["name_ru"] for c in data["categories"]] == ["Пальто"]
    assert [p["path"] for p in data["photos"]] == ["a.webp", "b.webp"]


async def test_create_with_several_locations(client, session):
    h, city, other, mall, rows, _ = await _setup(session)
    body = {
        "name": "Moda Line",
        "locations": [
            _in_mall(mall, floor=2, number="214"),
            {"mall_id": rows.id, "row": "14", "number": "32"},
            {"city_id": other.id, "address_ru": "ул. 1", "address_tk": "köç. 1"},
        ],
    }
    r = await client.post("/api/v1/admin/shops", json=body, headers=h)
    assert r.status_code == 201, r.text
    locs = r.json()["locations"]
    assert [loc["mall"]["id"] if loc["mall"] else None for loc in locs] == [mall.id, rows.id, None]
    assert [loc["city_id"] for loc in locs] == [city.id, city.id, other.id]
    assert locs[2]["address_ru"] == "ул. 1"


@pytest.mark.parametrize("locations", [None, []])
async def test_create_requires_location(client, session, locations):
    h, *_ = await _setup(session)
    body = {"name": "X"} if locations is None else {"name": "X", "locations": locations}
    r = await client.post("/api/v1/admin/shops", json=body, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("which", "extra", "detail"),
    [
        ("mall", {"number": "1"}, "floor_required"),
        ("mall", {"floor": 9, "number": "1"}, "floor_out_of_range"),
        ("mall", {"floor": 1, "row": "3", "number": "1"}, "row_not_allowed"),
        ("mall", {"floor": 1}, "number_required"),
        ("rows", {"number": "32"}, "row_required"),
        ("rows", {"row": "14", "floor": 1, "number": "32"}, "floor_not_allowed"),
    ],
)
async def test_location_rules(client, session, which, extra, detail):
    h, _, _, mall, rows, _ = await _setup(session)
    target = mall if which == "mall" else rows
    r = await client.post(
        "/api/v1/admin/shops",
        json={"name": "X", "locations": [{"mall_id": target.id, **extra}]},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == detail


async def test_any_bad_location_rejects_shop(client, session):
    h, _, _, mall, _, _ = await _setup(session)
    body = {"name": "X", "locations": [_in_mall(mall), {"mall_id": mall.id, "number": "2"}]}
    r = await client.post("/api/v1/admin/shops", json=body, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "floor_required"


async def test_standalone_requires_address(client, session):
    h, city, *_ = await _setup(session)
    r = await client.post(
        "/api/v1/admin/shops", json={"name": "X", "locations": [{"city_id": city.id}]}, headers=h
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "address_required"
    r = await client.post(
        "/api/v1/admin/shops",
        json={
            "name": "X",
            "locations": [{"city_id": city.id, "address_ru": "ул. 1", "address_tk": "köç. 1"}],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["locations"][0]["mall"] is None


async def test_standalone_requires_city(client, session):
    h, *_ = await _setup(session)
    r = await client.post(
        "/api/v1/admin/shops", json={"name": "X", "locations": [{"address_ru": "ул. 1"}]}, headers=h
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "city_required"


async def test_unknown_category(client, session):
    h, _, _, mall, _, _ = await _setup(session)
    r = await client.post(
        "/api/v1/admin/shops",
        json={"name": "X", "locations": [_in_mall(mall)], "category_ids": [999999]},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_category"


async def test_update_replaces_locations(client, session):
    h, city, _, mall, _, _ = await _setup(session)
    shop = await make_shop(session, "X", mall=mall, floor=1, number="5")
    r = await client.patch(
        f"/api/v1/admin/shops/{shop.id}",
        json={"locations": [{"city_id": city.id, "address_ru": "ул. 2", "address_tk": "köç. 2"}]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    [loc] = r.json()["locations"]
    assert loc["mall"] is None and loc["address_ru"] == "ул. 2"


@pytest.mark.parametrize("locations", [None, []])
async def test_update_cannot_remove_all_locations(client, session, locations):
    h, _, _, mall, _, _ = await _setup(session)
    shop = await make_shop(session, "X", mall=mall, floor=1)
    r = await client.patch(
        f"/api/v1/admin/shops/{shop.id}", json={"locations": locations}, headers=h
    )
    assert r.status_code == 422


async def test_update_without_locations_keeps_them(client, session):
    h, _, _, mall, _, _ = await _setup(session)
    shop = await make_shop(session, "X", mall=mall, floor=1, number="5")
    r = await client.patch(f"/api/v1/admin/shops/{shop.id}", json={"name": "Y"}, headers=h)
    assert r.status_code == 200
    assert [loc["number"] for loc in r.json()["locations"]] == ["5"]


async def test_update_replaces_categories(client, session):
    h, _, _, mall, _, coat = await _setup(session)
    shop = await make_shop(session, "X", mall=mall, floor=1, categories=[coat])
    r = await client.patch(f"/api/v1/admin/shops/{shop.id}", json={"category_ids": []}, headers=h)
    assert r.status_code == 200
    assert r.json()["categories"] == []


async def test_check_constraint_blocks_mixed_location(session):
    city = await make_city(session)
    mall = await make_mall(session, city)
    shop = await make_shop(session, "X", city=city)
    session.add(
        ShopLocation(
            shop_id=shop.id,
            position=1,
            city_id=city.id,
            mall_id=mall.id,
            number="1",
            address_ru="ул. 1",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_shop_detail_premium(client, session):
    city = await make_city(session)
    mall = await make_mall(session, city)
    shop = await make_shop(session, "Moda Line", mall=mall, floor=2, number="214")
    r = await client.get(f"/api/v1/shops/{shop.id}")
    assert r.status_code == 200
    assert r.json()["is_premium"] is False
    now = utcnow()
    session.add(
        Subscription(
            shop_id=shop.id,
            starts_at=now - timedelta(days=40),
            ends_at=now - timedelta(days=10),
            amount=Decimal("30"),
        )
    )
    await session.flush()
    assert (await client.get(f"/api/v1/shops/{shop.id}")).json()["is_premium"] is False
    session.add(
        Subscription(
            shop_id=shop.id,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=29),
            amount=Decimal("30"),
        )
    )
    await session.flush()
    body = (await client.get(f"/api/v1/shops/{shop.id}")).json()
    assert body["is_premium"] is True
    [loc] = body["locations"]
    assert loc["mall"]["name_ru"] == "Беркарар"
    assert loc["floor"] == 2 and loc["number"] == "214"


async def test_inactive_shop_404(client, session):
    city = await make_city(session)
    shop = await make_shop(session, "X", city=city, is_active=False)
    assert (await client.get(f"/api/v1/shops/{shop.id}")).status_code == 404


async def test_shop_in_inactive_mall_404(client, session):
    city = await make_city(session)
    mall = await make_mall(session, city, is_active=False)
    shop = await make_shop(session, "X", mall=mall, floor=1)
    assert (await client.get(f"/api/v1/shops/{shop.id}")).status_code == 404


async def test_public_detail_hides_location_in_inactive_mall(client, session):
    h, city, _, mall, _, _ = await _setup(session)
    closed = await make_mall(session, city, "Закрытый", is_active=False)
    shop = await make_shop(session, "X", mall=mall, floor=1)
    await add_location(session, shop, mall=closed, floor=1)
    public = (await client.get(f"/api/v1/shops/{shop.id}")).json()
    assert [loc["mall"]["id"] for loc in public["locations"]] == [mall.id]
    admin = (await client.get(f"/api/v1/admin/shops/{shop.id}", headers=h)).json()
    assert [loc["mall"]["id"] for loc in admin["locations"]] == [mall.id, closed.id]


async def test_admin_list_filters(client, session):
    h, city, _, mall, _, _ = await _setup(session)
    await make_shop(session, "Moda Line", mall=mall, floor=1)
    await make_shop(session, "Elegant", city=city)
    r = await client.get("/api/v1/admin/shops", params={"mall_id": mall.id}, headers=h)
    assert [s["name"] for s in r.json()["items"]] == ["Moda Line"]
    r = await client.get("/api/v1/admin/shops", params={"city_id": city.id}, headers=h)
    assert [s["name"] for s in r.json()["items"]] == ["Elegant", "Moda Line"]
    r = await client.get("/api/v1/admin/shops", params={"q": "eleg"}, headers=h)
    assert [s["name"] for s in r.json()["items"]] == ["Elegant"]


async def test_admin_delete_shop(client, session):
    h, city, *_ = await _setup(session)
    shop = await make_shop(session, "X", city=city)
    assert (await client.delete(f"/api/v1/admin/shops/{shop.id}", headers=h)).status_code == 204


async def test_admin_patch_shop_null_name_422(client, seller_world):
    w = seller_world
    r = await client.patch(f"/api/v1/admin/shops/{w.shop.id}", json={"name": None}, headers=w.ah)
    assert r.status_code == 422


async def test_nullable_fields_can_be_cleared(client, seller_world):
    w = seller_world
    r = await client.patch(
        f"/api/v1/admin/shops/{w.shop.id}", json={"how_to_find_ru": None}, headers=w.ah
    )
    assert r.status_code == 200
    assert r.json()["how_to_find_ru"] is None
