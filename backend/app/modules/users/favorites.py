from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.malls.models import Mall
from app.modules.malls.schemas import MallListItem
from app.modules.malls.service import get_mall_or_404, public_malls, to_list_items
from app.modules.shops.models import Shop
from app.modules.shops.schemas import ShopBrief
from app.modules.shops.service import get_shop_or_404, load_briefs, public_shops
from app.modules.users.models import User, favorite_shops, user_malls


async def add_favorite(session: AsyncSession, user: User, shop_id: int) -> None:
    await get_shop_or_404(session, shop_id, public=True)
    await session.execute(
        insert(favorite_shops).values(user_id=user.id, shop_id=shop_id).on_conflict_do_nothing()
    )
    await session.commit()


async def remove_favorite(session: AsyncSession, user: User, shop_id: int) -> None:
    await session.execute(
        delete(favorite_shops).where(
            favorite_shops.c.user_id == user.id, favorite_shops.c.shop_id == shop_id
        )
    )
    await session.commit()


async def list_favorites(session: AsyncSession, user: User) -> list[ShopBrief]:
    stmt = (
        public_shops()
        .join(favorite_shops, favorite_shops.c.shop_id == Shop.id)
        .where(favorite_shops.c.user_id == user.id)
        .order_by(favorite_shops.c.created_at.desc(), Shop.id.desc())
    )
    return await load_briefs(session, list(await session.scalars(stmt)))


async def is_favorite(session: AsyncSession, user: User | None, shop_id: int) -> bool:
    if user is None:
        return False
    found = await session.scalar(
        select(favorite_shops.c.shop_id).where(
            favorite_shops.c.user_id == user.id, favorite_shops.c.shop_id == shop_id
        )
    )
    return found is not None


async def add_mall(session: AsyncSession, user: User, mall_id: int) -> None:
    await get_mall_or_404(session, mall_id, public=True)
    await session.execute(
        insert(user_malls).values(user_id=user.id, mall_id=mall_id).on_conflict_do_nothing()
    )
    await session.commit()


async def remove_mall(session: AsyncSession, user: User, mall_id: int) -> None:
    await session.execute(
        delete(user_malls).where(user_malls.c.user_id == user.id, user_malls.c.mall_id == mall_id)
    )
    await session.commit()


async def list_malls(session: AsyncSession, user: User) -> list[MallListItem]:
    stmt = (
        public_malls()
        .join(user_malls, user_malls.c.mall_id == Mall.id)
        .where(user_malls.c.user_id == user.id)
        .order_by(Mall.sort_order, Mall.id)
    )
    return await to_list_items(session, list(await session.scalars(stmt)))


async def is_my_mall(session: AsyncSession, user: User | None, mall_id: int) -> bool:
    if user is None:
        return False
    found = await session.scalar(
        select(user_malls.c.mall_id).where(
            user_malls.c.user_id == user.id, user_malls.c.mall_id == mall_id
        )
    )
    return found is not None
