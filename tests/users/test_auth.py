from datetime import timedelta

from sqlalchemy import update

from app.modules.users.models import OtpCode
from app.timeutil import utcnow


async def _login(client, phone="+99365123456", code="1234"):
    r = await client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 204, r.text
    return await client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code})


async def _allow_new_request(session):
    # Push previous OTPs out of the 1/min rate-limit window.
    await session.execute(update(OtpCode).values(created_at=utcnow() - timedelta(minutes=2)))


async def test_otp_login_creates_user(client, sms):
    r = await _login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["phone"] == "+99365123456"
    assert body["user"]["role"] == "user"
    assert body["access_token"] and body["refresh_token"]
    assert len(sms.sent) == 1 and "1234" in sms.sent[0][1]


async def test_same_user_for_phone_variants(client, session, sms):
    first = (await _login(client, "+993 65 12 34 56")).json()["user"]["id"]
    await _allow_new_request(session)
    second = (await _login(client, "865123456")).json()["user"]["id"]
    assert first == second


async def test_wrong_code_then_lockout(client, sms):
    await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/otp/verify", json={"phone": "+99365123456", "code": "0000"}
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "otp_invalid"
    r = await client.post("/api/v1/auth/otp/verify", json={"phone": "+99365123456", "code": "1234"})
    assert r.status_code == 401
    assert r.json()["detail"] == "otp_expired"


async def test_expired_code(client, session, sms):
    await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    await session.execute(update(OtpCode).values(expires_at=utcnow() - timedelta(seconds=1)))
    r = await client.post("/api/v1/auth/otp/verify", json={"phone": "+99365123456", "code": "1234"})
    assert r.status_code == 401
    assert r.json()["detail"] == "otp_expired"


async def test_rate_limit(client, sms):
    r1 = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    r2 = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    assert r1.status_code == 204
    assert r2.status_code == 409
    assert r2.json()["detail"] == "otp_rate_limited"


async def test_hourly_rate_limit(client, session, sms):
    for _ in range(5):
        r = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
        assert r.status_code == 204
        await session.execute(
            update(OtpCode).values(created_at=OtpCode.created_at - timedelta(minutes=2))
        )
    r = await client.post("/api/v1/auth/otp/request", json={"phone": "+99365123456"})
    assert r.status_code == 409


async def test_invalid_phone_422(client, sms):
    r = await client.post("/api/v1/auth/otp/request", json={"phone": "123"})
    assert r.status_code == 422


async def test_refresh_rotates(client, sms):
    tokens = (await _login(client)).json()
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert r.json()["refresh_token"] != tokens["refresh_token"]
    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_logout_revokes(client, sms):
    tokens = (await _login(client)).json()
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
