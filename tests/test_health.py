async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_cors_preflight_allowed_for_configured_origin(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app import main
    from app.config import Settings

    monkeypatch.setattr(
        main, "get_settings", lambda: Settings(cors_origins=["http://localhost:3000"])
    )
    transport = ASGITransport(app=main.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.options(
            "/api/v1/cities",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
