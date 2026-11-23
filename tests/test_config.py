import pytest
from pydantic import ValidationError

from app.config import Settings


def test_prod_rejects_placeholder_secret():
    with pytest.raises(ValidationError):
        Settings(env="prod", jwt_secret="change-me-to-a-long-random-secret-of-32-plus-bytes")


def test_prod_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(env="prod", jwt_secret="short")


def test_prod_accepts_strong_secret():
    s = Settings(env="prod", jwt_secret="x" * 40)
    assert s.env == "prod"
