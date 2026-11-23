from fastapi import APIRouter
from sqlalchemy import select

from app.crud import paginate
from app.deps import AdminUser, SessionDep
from app.enums import ModerationStatus
from app.modules.moderation import service
from app.modules.moderation.models import ChangeRequest, EntityType
from app.modules.moderation.schemas import ChangeRequestAdminOut, ChangeRequestOut
from app.modules.promotions.schemas import ReviewIn
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin/change-requests", tags=["admin: moderation"])


@router.get("")
async def list_change_requests(
    _: AdminUser,
    session: SessionDep,
    page: PageDep,
    status: ModerationStatus | None = None,
    entity_type: EntityType | None = None,
) -> Page[ChangeRequestAdminOut]:
    stmt = select(ChangeRequest).order_by(ChangeRequest.id)
    if status is not None:
        stmt = stmt.where(ChangeRequest.status == status)
    if entity_type is not None:
        stmt = stmt.where(ChangeRequest.entity_type == entity_type)
    items, total = await paginate(session, stmt, page)
    out = [
        ChangeRequestAdminOut(
            **ChangeRequestOut.model_validate(cr).model_dump(),
            current=await service.current_snapshot(session, cr),
        )
        for cr in items
    ]
    return Page(items=out, total=total)


@router.post("/{cr_id}/approve")
async def approve(cr_id: int, admin: AdminUser, session: SessionDep) -> ChangeRequestOut:
    cr = await service.get_change_request_or_404(session, cr_id, lock=True)
    return ChangeRequestOut.model_validate(await service.approve_change_request(session, cr, admin))


@router.post("/{cr_id}/reject")
async def reject(
    cr_id: int, body: ReviewIn, admin: AdminUser, session: SessionDep
) -> ChangeRequestOut:
    cr = await service.get_change_request_or_404(session, cr_id, lock=True)
    return ChangeRequestOut.model_validate(
        await service.reject_change_request(session, cr, admin, body.comment)
    )
