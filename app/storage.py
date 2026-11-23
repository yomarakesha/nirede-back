import asyncio
import io
import uuid
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.timeutil import utcnow

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600


class Storage(Protocol):
    async def save(self, data: bytes, ext: str) -> str: ...

    def url(self, path: str) -> str: ...


class LocalStorage:
    def __init__(self, root: Path, base_url: str) -> None:
        self.root = root
        self.base_url = base_url.rstrip("/")

    async def save(self, data: bytes, ext: str) -> str:
        now = utcnow()
        rel = f"{now:%Y}/{now:%m}/{uuid.uuid4().hex}.{ext}"
        target = self.root / rel
        await asyncio.to_thread(_write, target, data)
        return rel

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path}"


def _write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def get_storage() -> Storage:
    settings = get_settings()
    return LocalStorage(settings.media_dir, settings.media_url)


def media_url(path: str | None) -> str | None:
    """URL for a stored path; used by Out schemas."""
    return get_storage().url(path) if path else None


def _to_webp(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = io.BytesIO()
            img.save(out, "WEBP", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_image") from exc


async def save_image(file: UploadFile, storage: Storage) -> str:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_image")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "image_too_large")
    webp = await asyncio.to_thread(_to_webp, data)
    return await storage.save(webp, "webp")
