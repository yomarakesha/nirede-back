from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.crud import get_or_404, paginate
from app.deps import AdminUser, SessionDep
from app.enums import UserRole
from app.modules.users.models import User
from app.modules.users.schemas import UserOut
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/users", tags=["admin: users"])


class RoleIn(BaseModel):
    role: UserRole


@router.get("")
async def list_users(
    _: AdminUser,
    session: SessionDep,
    page: PageDep,
    role: UserRole | None = None,
    q: str | None = None,
) -> Page[UserOut]:
    stmt = select(User).order_by(User.id.desc())
    if role is not None:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(or_(User.phone.contains(q, autoescape=True), User.name.ilike(f"%{q}%")))
    items, total = await paginate(session, stmt, page)
    return Page(items=[UserOut.model_validate(u) for u in items], total=total)


@router.patch("/{user_id}")
async def set_role(user_id: int, body: RoleIn, admin: AdminUser, session: SessionDep) -> UserOut:
    user = await get_or_404(session, User, user_id, "user_not_found")
    if user.id == admin.id and body.role != UserRole.admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_demote_self")
    user.role = body.role
    await session.commit()
    return UserOut.model_validate(user)
