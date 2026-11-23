from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://nirede:nirede@localhost:5433/nirede"
    test_database_url: str = "postgresql+asyncpg://nirede:nirede@localhost:5433/nirede_test"
    jwt_secret: str = "change-me"
    access_ttl_minutes: int = 30
    refresh_ttl_days: int = 30
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    media_dir: Path = Path("media")
    media_url: str = "/media"
    timezone: str = "Asia/Ashgabat"


@lru_cache
def get_settings() -> Settings:
    return Settings()
