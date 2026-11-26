from sqlalchemy import func, select

from app.modules.promotions.models import Promotion
from app.modules.shops.models import Shop, ShopLocation
from app.seed import PROMOTIONS, SHOPS, seed


async def test_seed_fills_data_and_is_idempotent(session):
    await seed(session)
    await seed(session)

    assert await session.scalar(select(func.count()).select_from(Shop)) == len(SHOPS)
    assert await session.scalar(select(func.count()).select_from(Promotion)) == len(PROMOTIONS)
    locations = sum(len(s["locations"]) for s in SHOPS)
    assert await session.scalar(select(func.count()).select_from(ShopLocation)) == locations


async def test_seeded_shops_are_public(session, client):
    await seed(session)

    resp = await client.get("/api/v1/search", params={"q": "Телефоны"})
    assert resp.status_code == 200, resp.text
    names = {s["name"] for g in resp.json()["groups"] for s in g["shops"]}
    assert "Mobile World" in names
