from tests.factories import auth_headers, make_user


async def test_me_requires_auth(client):
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_bad_token_401(client):
    r = await client.get("/api/v1/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_patch_me(client, session):
    user = await make_user(session)
    r = await client.patch(
        "/api/v1/me",
        json={"name": "Аман", "language": "tk", "notify_my_malls": False},
        headers=auth_headers(user),
    )
    assert r.status_code == 200, r.text
    me = (await client.get("/api/v1/me", headers=auth_headers(user))).json()
    assert me["name"] == "Аман"
    assert me["language"] == "tk"
    assert me["notify_my_malls"] is False
    assert me["notify_favorite_shops"] is True


async def test_patch_me_cannot_change_role(client, session):
    user = await make_user(session)
    r = await client.patch("/api/v1/me", json={"role": "admin"}, headers=auth_headers(user))
    assert r.status_code == 422
    me = (await client.get("/api/v1/me", headers=auth_headers(user))).json()
    assert me["role"] == "user"
