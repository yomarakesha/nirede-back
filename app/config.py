from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET = "change-me-to-a-long-random-secret-of-32-plus-bytes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | prod
    sms_debug_log: bool = False
    database_url: str = "postgresql+asyncpg://nirede:nirede@localhost:5433/nirede"
    test_database_url: str = "postgresql+asyncpg://nirede:nirede@localhost:5433/nirede_test"
    jwt_secret: str = PLACEHOLDER_SECRET
    access_ttl_minutes: int = 30
    refresh_ttl_days: int = 30
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    media_dir: Path = Path("media")
    media_url: str = "/media"
    timezone: str = "Asia/Ashgabat"

    @model_validator(mode="after")
    def _strong_secret_in_prod(self) -> "Settings":
        if self.env == "prod" and (
            self.jwt_secret == PLACEHOLDER_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be set to a random value of 32+ bytes in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
