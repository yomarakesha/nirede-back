"""Demo data for local development: python -m app.cli seed

Idempotent: every record is looked up by a natural key (city and mall name, category slug,
shop name, user phone, promotion title) and created only when missing, so the command can
run again on a database that already holds data.
"""

from datetime import time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ModerationStatus, UserRole
from app.modules.categories.models import Category
from app.modules.cities.models import City
from app.modules.malls.models import Mall, MallFloor, MallLayout
from app.modules.promotions.models import Promotion
from app.modules.shops.models import Shop, ShopLocation, Subscription, shop_categories
from app.modules.users.models import User, favorite_shops, user_malls
from app.timeutil import utcnow

CITIES = [("Ашхабад", "Aşgabat"), ("Мары", "Mary"), ("Туркменабат", "Türkmenabat")]

MALLS = [
    {
        "city": "Ашхабад",
        "name_ru": "Беркарар",
        "name_tk": "Berkarar",
        "address_ru": "пр. Атамурата Ниязова, 132",
        "address_tk": "Atamyrat Nyýazow şaýoly, 132",
        "description_ru": "Крупный торгово-развлекательный центр с кинотеатром и фудкортом.",
        "description_tk": "Kinoteatrly we nahar zolakly uly söwda-dynç alyş merkezi.",
        "phone": "+99312754000",
        "opens_at": time(10),
        "closes_at": time(22),
        "layout": MallLayout.floors,
        "floors_count": 4,
        "floors": [
            (1, "Одежда и обувь", "Eşik we aýakgap"),
            (2, "Электроника", "Elektronika"),
            (3, "Детские товары", "Çagalar harytlary"),
            (4, "Фудкорт и кино", "Nahar zolagy we kino"),
        ],
    },
    {
        "city": "Ашхабад",
        "name_ru": "Ашхабад",
        "name_tk": "Aşgabat",
        "address_ru": "ул. Андалиба, 1",
        "address_tk": "Andalyp köçesi, 1",
        "description_ru": "Торговый центр в центре города.",
        "description_tk": "Şäheriň merkezindäki söwda merkezi.",
        "phone": "+99312480000",
        "opens_at": time(9),
        "closes_at": time(21),
        "layout": MallLayout.floors,
        "floors_count": 3,
        "floors": [
            (1, "Косметика и аксессуары", "Kosmetika we aksessuarlar"),
            (2, "Одежда", "Eşik"),
            (3, "Товары для дома", "Öý harytlary"),
        ],
    },
    {
        "city": "Ашхабад",
        "name_ru": "Гулистан",
        "name_tk": "Gülistan",
        "address_ru": "ул. Пушкина, 20",
        "address_tk": "Puşkin köçesi, 20",
        "description_ru": "Русский базар: ряды с одеждой, тканями и бытовыми товарами.",
        "description_tk": "Rus bazary: eşik, mata we hojalyk harytlary bolan hatarlar.",
        "phone": None,
        "opens_at": time(8),
        "closes_at": time(18),
        "layout": MallLayout.rows,
        "floors_count": None,
        "floors": [],
    },
    {
        "city": "Мары",
        "name_ru": "Мары Сапар",
        "name_tk": "Mary Sapar",
        "address_ru": "ул. Махтумкули, 45",
        "address_tk": "Magtymguly köçesi, 45",
        "description_ru": "Торговый центр Мары.",
        "description_tk": "Marynyň söwda merkezi.",
        "phone": "+99352260000",
        "opens_at": time(9),
        "closes_at": time(21),
        "layout": MallLayout.floors,
        "floors_count": 2,
        "floors": [
            (1, "Одежда и обувь", "Eşik we aýakgap"),
            (2, "Электроника и дом", "Elektronika we öý"),
        ],
    },
]

# (slug, name_ru, name_tk, aliases_ru, aliases_tk, children)
CATEGORIES = [
    (
        "women",
        "Женщинам",
        "Aýallara",
        "женская одежда",
        "aýal eşikleri",
        [
            ("women-outerwear", "Верхняя одежда", "Daşky eşik", "пальто куртки", "palto kurtka"),
            ("women-dresses", "Платья", "Köýnekler", "платье", "köýnek"),
            ("women-shoes", "Женская обувь", "Aýal aýakgaplary", "туфли сапоги", "tufli"),
        ],
    ),
    (
        "men",
        "Мужчинам",
        "Erkeklere",
        "мужская одежда",
        "erkek eşikleri",
        [
            ("men-suits", "Костюмы", "Kostýumlar", "пиджак брюки", "pijak balak"),
            ("men-shoes", "Мужская обувь", "Erkek aýakgaplary", "ботинки кроссовки", "krossowka"),
        ],
    ),
    (
        "kids",
        "Детям",
        "Çagalara",
        "детская одежда",
        "çaga eşikleri",
        [
            ("kids-clothes", "Детская одежда", "Çaga eşikleri", None, None),
            ("toys", "Игрушки", "Oýunjaklar", "игрушка", "oýunjak"),
        ],
    ),
    (
        "electronics",
        "Электроника",
        "Elektronika",
        "техника",
        "tehnika",
        [
            ("phones", "Телефоны", "Telefonlar", "смартфон айфон", "smartfon"),
            ("laptops", "Ноутбуки", "Noutbuklar", "ноутбук компьютер", "noutbuk kompýuter"),
            (
                "gadgets",
                "Аксессуары и гаджеты",
                "Aksessuarlar we gajetler",
                "наушники зарядка",
                "nauşnik",
            ),
        ],
    ),
    (
        "beauty",
        "Красота",
        "Gözellik",
        "косметика парфюм",
        "kosmetika atyr",
        [
            ("cosmetics", "Косметика", "Kosmetika", "макияж крем", "krem"),
            ("perfume", "Парфюмерия", "Atyrlar", "духи", "atyr"),
        ],
    ),
    (
        "home",
        "Дом",
        "Öý",
        "товары для дома",
        "öý harytlary",
        [
            ("kitchen", "Кухня", "Aşhana", "посуда", "gap-gaç"),
            ("textile", "Текстиль", "Dokma", "ткани шторы", "mata perde"),
        ],
    ),
]

# Location: ("mall", mall name_ru, floor, row, number)
#        or ("city", city name_ru, address_ru, address_tk)
SHOPS = [
    {
        "name": "Lady Style",
        "phone": "+99365100001",
        "categories": ["women-outerwear", "women-dresses"],
        "how_to_find_ru": "От главного входа налево, третий павильон.",
        "how_to_find_tk": "Esasy girelgeden çepe, üçünji dükan.",
        "locations": [("mall", "Беркарар", 1, None, "12"), ("mall", "Ашхабад", 2, None, "5")],
        "premium": True,
    },
    {
        "name": "Shoe Point",
        "phone": "+99365100002",
        "categories": ["women-shoes", "men-shoes"],
        "locations": [("mall", "Беркарар", 1, None, "18")],
    },
    {
        "name": "Gentleman",
        "phone": "+99365100003",
        "categories": ["men-suits"],
        "locations": [("mall", "Ашхабад", 2, None, "14")],
    },
    {
        "name": "Bäbek",
        "phone": "+99365100004",
        "categories": ["kids-clothes", "toys"],
        "locations": [("mall", "Беркарар", 3, None, "3")],
        "premium": True,
    },
    {
        "name": "Mobile World",
        "phone": "+99365100005",
        "categories": ["phones", "gadgets"],
        "locations": [
            ("mall", "Беркарар", 2, None, "7"),
            ("city", "Ашхабад", "ул. Битарап Туркменистан, 54", "Bitarap Türkmenistan köç., 54"),
            ("mall", "Мары Сапар", 2, None, "2"),
        ],
        "premium": True,
    },
    {
        "name": "TechnoLand",
        "phone": "+99365100006",
        "categories": ["laptops", "gadgets", "phones"],
        "locations": [("mall", "Беркарар", 2, None, "21")],
    },
    {
        "name": "Gözel",
        "phone": "+99365100007",
        "categories": ["cosmetics", "perfume"],
        "locations": [("mall", "Ашхабад", 1, None, "9")],
    },
    {
        "name": "Atyr House",
        "phone": "+99365100008",
        "categories": ["perfume"],
        "locations": [("city", "Ашхабад", "пр. Махтумкули, 77", "Magtymguly şaýoly, 77")],
    },
    {
        "name": "Ýüpek Mata",
        "phone": "+99365100009",
        "categories": ["textile"],
        "how_to_find_ru": "Ряд с тканями, ближе к выходу на ул. Пушкина.",
        "how_to_find_tk": "Mata hatary, Puşkin köçesine çykalgä ýakyn.",
        "locations": [("mall", "Гулистан", None, "A", "15")],
    },
    {
        "name": "Öý Goşlary",
        "phone": "+99365100010",
        "categories": ["kitchen", "textile"],
        "locations": [("mall", "Гулистан", None, "C", "4"), ("mall", "Ашхабад", 3, None, "1")],
    },
    {
        "name": "Moda Mary",
        "phone": "+99365100011",
        "categories": ["women-dresses", "men-suits", "kids-clothes"],
        "locations": [("mall", "Мары Сапар", 1, None, "6")],
    },
    {
        "name": "Sport Life",
        "phone": "+99365100012",
        "categories": ["men-shoes", "women-shoes"],
        "locations": [
            ("city", "Туркменабат", "ул. Шабендэ, 12", "Şabende köç., 12"),
            ("mall", "Гулистан", None, "B", "8"),
        ],
    },
]

# (shop, title_ru, title_tk, badge, description_ru, starts in days, lasts days, status)
PROMOTIONS = [
    (
        "Lady Style",
        "−30% на пальто",
        "Paltolara −30%",
        "−30%",
        "Скидка на всю коллекцию верхней одежды.",
        -2,
        14,
        ModerationStatus.approved,
    ),
    (
        "Mobile World",
        "Чехол в подарок",
        "Gap sowgat",
        "Подарок",
        "При покупке любого смартфона — чехол бесплатно.",
        -1,
        7,
        ModerationStatus.approved,
    ),
    (
        "Bäbek",
        "Распродажа игрушек",
        "Oýunjaklaryň arzanladyşy",
        "−50%",
        "Скидки до 50% на игрушки к Новому году.",
        3,
        10,
        ModerationStatus.approved,
    ),
    (
        "Gözel",
        "Неделя парфюмерии",
        "Atyr hepdesi",
        "−20%",
        "Скидка на всю парфюмерию.",
        0,
        7,
        ModerationStatus.pending,
    ),
    (
        "TechnoLand",
        "Ноутбуки в рассрочку",
        "Noutbuklar möhletleýin",
        "0%",
        "Рассрочка без переплаты на 6 месяцев.",
        -30,
        10,
        ModerationStatus.approved,
    ),
]

SELLER_PHONE = "+99365200001"
SELLER_SHOP = "Lady Style"
DEMO_USER_PHONE = "+99365200002"
DEMO_USER_FAVORITES = ["Lady Style", "Mobile World", "Gözel"]
DEMO_USER_MALLS = ["Беркарар"]


async def _get_or_add(session: AsyncSession, model, lookup: dict, **values):
    obj = await session.scalar(select(model).filter_by(**lookup))
    if obj is None:
        obj = model(**lookup, **values)
        session.add(obj)
        await session.flush()
    return obj


async def seed(session: AsyncSession) -> None:
    now = utcnow()

    cities = {}
    for name_ru, name_tk in CITIES:
        cities[name_ru] = await _get_or_add(session, City, {"name_ru": name_ru}, name_tk=name_tk)

    malls = {}
    for sort_order, data in enumerate(MALLS):
        data = dict(data)
        city, floors = cities[data.pop("city")], data.pop("floors")
        mall = await _get_or_add(
            session,
            Mall,
            {"name_ru": data.pop("name_ru"), "city_id": city.id},
            sort_order=sort_order,
            **data,
        )
        for number, summary_ru, summary_tk in floors:
            await _get_or_add(
                session,
                MallFloor,
                {"mall_id": mall.id, "number": number},
                summary_ru=summary_ru,
                summary_tk=summary_tk,
            )
        malls[mall.name_ru] = mall

    categories = {}
    for root_order, (slug, name_ru, name_tk, al_ru, al_tk, children) in enumerate(CATEGORIES):
        root = await _get_or_add(
            session,
            Category,
            {"slug": slug},
            name_ru=name_ru,
            name_tk=name_tk,
            search_aliases_ru=al_ru,
            search_aliases_tk=al_tk,
            sort_order=root_order,
        )
        for order, (c_slug, c_ru, c_tk, c_al_ru, c_al_tk) in enumerate(children):
            categories[c_slug] = await _get_or_add(
                session,
                Category,
                {"slug": c_slug},
                parent_id=root.id,
                name_ru=c_ru,
                name_tk=c_tk,
                search_aliases_ru=c_al_ru,
                search_aliases_tk=c_al_tk,
                sort_order=order,
            )

    shops = {}
    for data in SHOPS:
        shop = await session.scalar(select(Shop).where(Shop.name == data["name"]))
        if shop is None:
            shop = Shop(
                name=data["name"],
                phone=data["phone"],
                opens_at=time(10),
                closes_at=time(21),
                how_to_find_ru=data.get("how_to_find_ru"),
                how_to_find_tk=data.get("how_to_find_tk"),
            )
            session.add(shop)
            await session.flush()
            for position, loc in enumerate(data["locations"]):
                if loc[0] == "mall":
                    _, mall_name, floor, row, number = loc
                    mall = malls[mall_name]
                    location = ShopLocation(
                        mall_id=mall.id,
                        city_id=mall.city_id,
                        floor=floor,
                        row=row,
                        number=number,
                    )
                else:
                    _, city_name, address_ru, address_tk = loc
                    location = ShopLocation(
                        city_id=cities[city_name].id,
                        address_ru=address_ru,
                        address_tk=address_tk,
                    )
                location.shop_id, location.position = shop.id, position
                session.add(location)
            await session.execute(
                shop_categories.insert(),
                [{"shop_id": shop.id, "category_id": categories[s].id} for s in data["categories"]],
            )
            if data.get("premium"):
                session.add(
                    Subscription(
                        shop_id=shop.id,
                        starts_at=now - timedelta(days=1),
                        ends_at=now + timedelta(days=29),
                        amount=Decimal("30"),
                        note="seed",
                    )
                )
            await session.flush()
        shops[shop.name] = shop

    for shop_name, title_ru, title_tk, badge, desc_ru, start, days, status in PROMOTIONS:
        starts_at = now + timedelta(days=start)
        await _get_or_add(
            session,
            Promotion,
            {"shop_id": shops[shop_name].id, "title_ru": title_ru},
            title_tk=title_tk,
            badge=badge,
            description_ru=desc_ru,
            description_tk=None,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=days),
            status=status,
            # Already-running promotions are marked announced so seeding sends no pushes.
            announced_at=now if starts_at <= now else None,
        )

    seller = await _get_or_add(
        session, User, {"phone": SELLER_PHONE}, name="Айна (продавец)", role=UserRole.seller
    )
    shops[SELLER_SHOP].owner_id = seller.id

    user = await _get_or_add(session, User, {"phone": DEMO_USER_PHONE}, name="Мерген")
    for name in DEMO_USER_FAVORITES:
        await session.execute(
            insert(favorite_shops)
            .values(user_id=user.id, shop_id=shops[name].id)
            .on_conflict_do_nothing()
        )
    for name in DEMO_USER_MALLS:
        await session.execute(
            insert(user_malls)
            .values(user_id=user.id, mall_id=malls[name].id)
            .on_conflict_do_nothing()
        )

    await session.commit()
