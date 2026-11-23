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


async def make_city(session, name_ru: str = "Ашхабад", name_tk: str = "Aşgabat"):
    from app.modules.cities.models import City

    city = City(name_ru=name_ru, name_tk=name_tk)
    session.add(city)
    await session.flush()
    return city


async def make_mall(session, city, name: str = "Беркарар", layout: str = "floors", **kw):
    from app.modules.malls.models import Mall

    defaults = {
        "name_ru": name,
        "name_tk": name,
        "address_ru": "ул. Ататюрка, 80",
        "address_tk": "Atatürk köç., 80",
        "floors_count": 4 if layout == "floors" else None,
    }
    mall = Mall(city_id=city.id, layout=layout, **{**defaults, **kw})
    session.add(mall)
    await session.flush()
    return mall
