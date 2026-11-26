from app.cli import create_admin
from tests.factories import make_user


async def test_create_admin_new_user(session):
    user = await create_admin(session, "865123456")
    assert user.phone == "+99365123456"
    assert user.role == "admin"


async def test_create_admin_promotes_existing(session):
    existing = await make_user(session)
    user = await create_admin(session, "+99365123456")
    assert user.id == existing.id
    assert user.role == "admin"
