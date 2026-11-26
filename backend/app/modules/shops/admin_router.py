from fastapi import APIRouter, status
from sqlalchemy import select

from app.crud import delete_or_409, paginate
from app.deps import AdminUser, SessionDep
from app.modules.shops import service
from app.modules.shops.models import Shop
from app.modules.shops.schemas import ShopAdminOut, ShopBrief, ShopCreate, ShopUpdate
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/shops", tags=["admin: shops"])


@router.get("")
async def list_shops(
    _: AdminUser,
    session: SessionDep,
    page: PageDep,
    mall_id: int | None = None,
    city_id: int | None = None,
    q: str | None = None,
) -> Page[ShopBrief]:
    stmt = select(Shop).order_by(Shop.name, Shop.id)
    if mall_id is not None or city_id is not None:
        stmt = stmt.where(service.located(city_id=city_id, mall_id=mall_id, public=False))
    if q:
        stmt = stmt.where(Shop.name.ilike(f"%{q}%"))
    items, total = await paginate(session, stmt, page)
    return Page(items=await service.load_briefs(session, items, public=False), total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_shop(body: ShopCreate, _: AdminUser, session: SessionDep) -> ShopAdminOut:
    shop = await service.create_shop(session, body)
    return await service.load_detail(session, shop, admin=True)


@router.get("/{shop_id}")
async def get_shop(shop_id: int, _: AdminUser, session: SessionDep) -> ShopAdminOut:
    shop = await service.get_shop_or_404(session, shop_id, public=False)
    return await service.load_detail(session, shop, admin=True)


@router.patch("/{shop_id}")
async def update_shop(
    shop_id: int, body: ShopUpdate, _: AdminUser, session: SessionDep
) -> ShopAdminOut:
    shop = await service.get_shop_or_404(session, shop_id, public=False)
    await service.update_shop(session, shop, body)
    return await service.load_detail(session, shop, admin=True)


@router.delete("/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop(shop_id: int, _: AdminUser, session: SessionDep) -> None:
    shop = await service.get_shop_or_404(session, shop_id, public=False)
    await delete_or_409(session, shop, "shop_in_use")
