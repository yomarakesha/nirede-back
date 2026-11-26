import io

import pytest
from PIL import Image

from app.storage import LocalStorage, get_storage
from tests.factories import auth_headers, make_admin, make_user


@pytest.fixture
def storage(app, tmp_path):
    st = LocalStorage(tmp_path, "/media")
    app.dependency_overrides[get_storage] = lambda: st
    return st


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "green").save(buf, "PNG")
    return buf.getvalue()


async def test_upload_png_returns_webp_path(client, session, storage, tmp_path):
    h = auth_headers(await make_admin(session))
    files = {"file": ("big.png", _png(2000, 1000), "image/png")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["path"].endswith(".webp")
    assert body["url"] == f"/media/{body['path']}"
    with Image.open(tmp_path / body["path"]) as img:
        assert img.size == (1600, 800)


async def test_reject_non_image(client, session, storage):
    h = auth_headers(await make_admin(session))
    files = {"file": ("a.txt", b"hello", "text/plain")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_image"


async def test_reject_fake_image_bytes(client, session, storage):
    h = auth_headers(await make_admin(session))
    files = {"file": ("a.png", b"not really a png", "image/png")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "invalid_image"


async def test_reject_too_large(client, session, storage):
    h = auth_headers(await make_admin(session))
    files = {"file": ("big.png", b"\0" * (5 * 1024 * 1024 + 1), "image/png")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "image_too_large"


async def test_user_cannot_upload(client, session, storage):
    h = auth_headers(await make_user(session))
    files = {"file": ("a.png", _png(10, 10), "image/png")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 403
    r = await client.post("/api/v1/seller/uploads", files=files, headers=h)
    assert r.status_code == 403


async def test_seller_can_upload(client, session, storage):
    h = auth_headers(await make_user(session, role="seller"))
    files = {"file": ("a.png", _png(10, 10), "image/png")}
    r = await client.post("/api/v1/seller/uploads", files=files, headers=h)
    assert r.status_code == 201


async def test_reject_huge_pixel_count(client, session, storage):
    # 12000x12000 single-colour PNG compresses to a few hundred KB but decodes to ~430 MB.
    h = auth_headers(await make_admin(session))
    buf = io.BytesIO()
    Image.new("1", (12000, 12000)).save(buf, "PNG")
    assert len(buf.getvalue()) < 5 * 1024 * 1024
    files = {"file": ("bomb.png", buf.getvalue(), "image/png")}
    r = await client.post("/api/v1/admin/uploads", files=files, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "image_too_large"
