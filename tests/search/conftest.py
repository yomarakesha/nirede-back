from types import SimpleNamespace

import pytest

from tests.factories import make_category, make_city, make_mall, make_shop


@pytest.fixture
async def world(session):
    """Seed mirroring the Figma screens."""
    city = await make_city(session)
    berkarar = await make_mall(session, city, "Беркарар", floors_count=4)
    arkach = await make_mall(session, city, "Аркач", floors_count=3)
    mall = await make_mall(session, city, "Ашхабад Молл", floors_count=4)
    market = await make_mall(session, city, "Толкучка", layout="rows")

    women = await make_category(session, "Женщинам", name_tk="Aýallara", slug="women")
    w_outer = await make_category(
        session, "Верхняя одежда", women, name_tk="Daşky eşik", slug="w-outer"
    )
    w_coat = await make_category(
        session,
        "Пальто",
        w_outer,
        name_tk="Palto",
        slug="w-coat",
        search_aliases_ru="женское пальто женские пальто",
    )
    men = await make_category(session, "Мужчинам", name_tk="Erkeklere", slug="men")
    m_outer = await make_category(
        session, "Верхняя одежда", men, name_tk="Daşky eşik", slug="m-outer"
    )
    m_coat = await make_category(session, "Пальто", m_outer, name_tk="Palto", slug="m-coat")
    kids = await make_category(session, "Детям", name_tk="Çagalara", slug="kids")
    k_outer = await make_category(
        session, "Верхняя одежда", kids, name_tk="Daşky eşik", slug="k-outer"
    )
    k_fur = await make_category(session, "Шубы", k_outer, name_tk="Şubalar", slug="k-fur")

    c = [w_coat]
    await make_shop(
        session, "Moda Line", mall=berkarar, floor=2, number="214", categories=c, premium=True
    )
    await make_shop(
        session, "Lady Style", mall=berkarar, floor=2, number="217", categories=c, premium=True
    )
    await make_shop(session, "Palto House", mall=berkarar, floor=1, number="116", categories=c)
    await make_shop(session, "Elegant", mall=berkarar, floor=2, number="216", categories=c)
    await make_shop(session, "Zamana", mall=arkach, floor=1, number="24", categories=c)
    await make_shop(session, "Ýüpek", mall=market, row="14", number="32", categories=c)
    await make_shop(session, "Город Пальто", city=city, categories=c)
    await make_shop(session, "Men Coats", mall=mall, floor=1, number="5", categories=[m_coat])
    await make_shop(
        session, "Hidden", mall=berkarar, floor=3, number="300", categories=c, is_active=False
    )

    return SimpleNamespace(
        city=city,
        berkarar=berkarar,
        arkach=arkach,
        mall=mall,
        market=market,
        women=women,
        w_outer=w_outer,
        w_coat=w_coat,
        m_coat=m_coat,
        k_outer=k_outer,
        k_fur=k_fur,
    )
