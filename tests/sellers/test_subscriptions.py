from datetime import timedelta
from decimal import Decimal

from app.modules.shops.models import Subscription
from app.timeutil import utcnow
from tests.factories import auth_headers, make_admin, make_city, make_shop


async def test_create_subscription_defaults(client, session):
    h = auth_headers(await make_admin(session))
    shop = await make_shop(session, "X", city=await make_city(session))
    r = await client.post(f"/api/v1/admin/shops/{shop.id}/subscriptions", json={}, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["amount"]) == Decimal("30")
    from datetime import datetime

    starts = datetime.fromisoformat(body["starts_at"])
    ends = datetime.fromisoformat(body["ends_at"])
    assert ends - starts == timedelta(days=30)
    assert (await client.get(f"/api/v1/shops/{shop.id}")).json()["is_premium"] is True


async def test_subscription_extends_from_end(client, session):
    h = auth_headers(await make_admin(session))
    shop = await make_shop(session, "X", city=await make_city(session))
    now = utcnow()
    current_end = now + timedelta(days=10)
    session.add(
        Subscription(
            shop_id=shop.id,
            starts_at=now - timedelta(days=20),
            ends_at=current_end,
            amount=Decimal("30"),
        )
    )
    await session.flush()
    r = await client.post(
        f"/api/v1/admin/shops/{shop.id}/subscriptions", json={"days": 30, "note": "нал"}, headers=h
    )
    from datetime import datetime

    assert datetime.fromisoformat(r.json()["starts_at"]) == current_end
    r = await client.get(f"/api/v1/admin/shops/{shop.id}/subscriptions", headers=h)
    assert len(r.json()) == 2


async def test_subscription_unknown_shop_404(client, session):
    h = auth_headers(await make_admin(session))
    r = await client.post("/api/v1/admin/shops/999999/subscriptions", json={}, headers=h)
    assert r.status_code == 404
