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

    shop = Shop(name=name, **kw)
    session.add(shop)
    await session.flush()
    await add_location(session, shop, mall=mall, city=city, floor=floor, row=row, number=number)
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


async def add_location(
    session,
    shop,
    *,
    mall=None,
    city=None,
    floor=None,
    row=None,
    number=None,
    address_ru="ул. Гёроглы, 1",
    address_tk="Görogly köç., 1",
):
    from sqlalchemy import func, select

    from app.modules.shops.models import ShopLocation

    position = await session.scalar(select(func.count()).where(ShopLocation.shop_id == shop.id))
    if mall is not None:
        loc = ShopLocation(
            mall_id=mall.id, city_id=mall.city_id, floor=floor, row=row, number=number or "1"
        )
    else:
        loc = ShopLocation(city_id=city.id, address_ru=address_ru, address_tk=address_tk)
    loc.shop_id = shop.id
    loc.position = position
    session.add(loc)
    await session.flush()
    return loc


async def make_promotion(session, shop, title: str = "−30% на пальто", *, status="approved", **kw):
    from datetime import timedelta

    from app.modules.promotions.models import Promotion
    from app.timeutil import utcnow

    now = utcnow()
    promo = Promotion(
        shop_id=shop.id,
        title_ru=title,
        title_tk=kw.pop("title_tk", title),
        badge=kw.pop("badge", "−30%"),
        starts_at=kw.pop("starts_at", now - timedelta(days=1)),
        ends_at=kw.pop("ends_at", now + timedelta(days=10)),
        status=status,
        **kw,
    )
    session.add(promo)
    await session.flush()
    return promo
