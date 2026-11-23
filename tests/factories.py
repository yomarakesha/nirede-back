from app.modules.users.models import User
from app.security import create_access_token


async def make_user(session, phone: str = "+99365123456", role: str = "user", **kw) -> User:
    user = User(phone=phone, role=role, **kw)
    session.add(user)
    await session.flush()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


async def make_admin(session, phone: str = "+99361000000") -> User:
    return await make_user(session, phone=phone, role="admin")
