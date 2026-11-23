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


async def make_category(session, name: str, parent=None, **kw):
    from app.modules.categories.models import Category

    slug = kw.pop("slug", None) or f"{name}-{id(object())}"
    cat = Category(
        name_ru=name,
        name_tk=kw.pop("name_tk", name),
        slug=slug,
        parent_id=parent.id if parent else None,
        **kw,
    )
    session.add(cat)
    await session.flush()
    return cat


async def make_women_tree(session):
    """Женщинам › Верхняя одежда › Пальто"""
    root = await make_category(session, "Женщинам", name_tk="Aýallara")
    outer = await make_category(session, "Верхняя одежда", root, name_tk="Daşky eşik")
    coat = await make_category(session, "Пальто", outer, name_tk="Palto")
    return root, outer, coat


async def make_shop(
    session,
    name: str,
    *,
    mall=None,
    city=None,
    floor=None,
    row=None,
    number=None,
    categories=(),
    premium: bool = False,
    **kw,
):
    from datetime import timedelta
    from decimal import Decimal

    from app.modules.shops.models import Shop, Subscription, shop_categories
    from app.timeutil import utcnow

    if mall is not None:
        kw.setdefault("city_id", mall.city_id)
        number = number or "1"
    else:
        kw.setdefault("city_id", city.id)
        kw.setdefault("address_ru", "ул. Гёроглы, 1")
        kw.setdefault("address_tk", "Görogly köç., 1")
    shop = Shop(
        name=name,
        mall_id=mall.id if mall else None,
        floor=floor,
        row=row,
        number=number,
        **kw,
    )
    session.add(shop)
    await session.flush()
    for cat in categories:
        await session.execute(shop_categories.insert().values(shop_id=shop.id, category_id=cat.id))
    if premium:
        now = utcnow()
        session.add(
            Subscription(
                shop_id=shop.id,
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=29),
                amount=Decimal("30"),
            )
        )
    await session.flush()
    return shop
