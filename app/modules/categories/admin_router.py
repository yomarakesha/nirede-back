from fastapi import APIRouter, status
from sqlalchemy import select

from app.crud import apply_update, delete_or_409, paginate
from app.deps import AdminUser, SessionDep
from app.modules.categories import service
from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryAdminOut, CategoryCreate, CategoryUpdate
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/categories", tags=["admin: categories"])


@router.get("")
async def list_categories(
    _: AdminUser, session: SessionDep, page: PageDep, parent_id: int | None = None
) -> Page[CategoryAdminOut]:
    stmt = select(Category).order_by(Category.sort_order, Category.id)
    if parent_id is not None:
        stmt = stmt.where(Category.parent_id == parent_id)
    items, total = await paginate(session, stmt, page)
    return Page(items=[CategoryAdminOut.model_validate(c) for c in items], total=total)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate, _: AdminUser, session: SessionDep
) -> CategoryAdminOut:
    if body.parent_id is not None:
        await service.check_parent(session, None, body.parent_id)
    category = Category(**body.model_dump())
    session.add(category)
    await service.commit_or_slug_conflict(session)
    return CategoryAdminOut.model_validate(category)


@router.get("/{category_id}")
async def get_category(category_id: int, _: AdminUser, session: SessionDep) -> CategoryAdminOut:
    return CategoryAdminOut.model_validate(await service.get_category_or_404(session, category_id))


@router.patch("/{category_id}")
async def update_category(
    category_id: int, body: CategoryUpdate, _: AdminUser, session: SessionDep
) -> CategoryAdminOut:
    category = await service.get_category_or_404(session, category_id)
    if body.parent_id is not None:
        await service.check_parent(session, category, body.parent_id)
    apply_update(category, body)
    await service.commit_or_slug_conflict(session)
    return CategoryAdminOut.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, _: AdminUser, session: SessionDep) -> None:
    category = await service.get_category_or_404(session, category_id)
    await delete_or_409(session, category, "category_in_use")
