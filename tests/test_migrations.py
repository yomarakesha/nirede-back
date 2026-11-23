import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

DB = "nirede_migration_check"


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], env=env, capture_output=True, text=True
    )


async def test_migrations_match_models():
    base = get_settings().test_database_url
    admin = create_async_engine(base, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        await conn.execute(text(f"CREATE DATABASE {DB}"))
    try:
        url = base.rsplit("/", 1)[0] + f"/{DB}"
        up = _alembic(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        check = _alembic(url, "check")
        assert check.returncode == 0, check.stdout + check.stderr
        down = _alembic(url, "downgrade", "base")
        assert down.returncode == 0, down.stderr
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)"))
        await admin.dispose()
