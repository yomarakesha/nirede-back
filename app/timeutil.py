from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def is_open(opens_at: time | None, closes_at: time | None, at: datetime) -> bool:
    if opens_at is None or closes_at is None:
        return False
    local = at.astimezone(ZoneInfo(get_settings().timezone)).time()
    if opens_at < closes_at:
        return opens_at <= local < closes_at
    # Overnight hours, e.g. 10:00-02:00.
    return local >= opens_at or local < closes_at
