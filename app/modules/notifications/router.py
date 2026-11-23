from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.crud import paginate
from app.deps import CurrentUser, SessionDep
from app.modules.notifications import service
from app.modules.notifications.models import Notification
from app.modules.notifications.push import PushSender, get_push_sender
from app.modules.notifications.schemas import DeviceIn, NotificationOut, UnreadCount
from app.pagination import Page, PageDep

router = APIRouter(prefix="/me", tags=["me"])

PushDep = Annotated[PushSender, Depends(get_push_sender)]


@router.get("/notifications")
async def list_notifications(
    user: CurrentUser, session: SessionDep, page: PageDep
) -> Page[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    items, total = await paginate(session, stmt, page)
    return Page(items=[NotificationOut.model_validate(n) for n in items], total=total)


@router.get("/notifications/unread-count")
async def unread_count(user: CurrentUser, session: SessionDep) -> UnreadCount:
    return UnreadCount(count=await service.unread_count(session, user))


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(user: CurrentUser, session: SessionDep) -> None:
    await service.mark_all_read(session, user)


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(notification_id: int, user: CurrentUser, session: SessionDep) -> None:
    await service.mark_read(session, user, notification_id)


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(body: DeviceIn, user: CurrentUser, session: SessionDep) -> None:
    await service.register_device(session, user, body.token, body.platform)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(token: str, user: CurrentUser, session: SessionDep) -> None:
    await service.remove_device(session, user, token)
