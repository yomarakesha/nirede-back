from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401  registers all models on Base.metadata
from app.config import get_settings
from app.db import Base, get_session
from app.main import create_app
from app.modules.users import service as users_service
from app.modules.users.sms import get_sms_sender
from tests.factories import auth_headers, make_admin, make_city, make_mall, make_shop, make_user


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(get_settings().test_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
def app(session):
    app = create_app()

    async def _get_session():
        yield session

    app.dependency_overrides[get_session] = _get_session
    return app


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def seller_world(session):
    admin = await make_admin(session)
    seller = await make_user(session, phone="+99365000011", role="seller")
    city = await make_city(session)
    mall = await make_mall(session, city)
    shop = await make_shop(
        session,
        "Moda Line",
        mall=mall,
        floor=2,
        number="214",
        owner_id=seller.id,
        premium=True,
        how_to_find_ru="Старый текст",
    )
    return SimpleNamespace(
        admin=admin,
        ah=auth_headers(admin),
        seller=seller,
        sh=auth_headers(seller),
        city=city,
        mall=mall,
        shop=shop,
    )


class FakeSms:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> None:
        self.sent.append((phone, text))


@pytest.fixture
def sms(app, monkeypatch):
    fake = FakeSms()
    app.dependency_overrides[get_sms_sender] = lambda: fake
    monkeypatch.setattr(users_service, "generate_otp", lambda: "1234")
    return fake
