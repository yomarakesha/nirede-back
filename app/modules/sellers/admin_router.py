from fastapi import APIRouter, status
from sqlalchemy import select

from app.crud import paginate
from app.deps import AdminUser, SessionDep
from app.enums import ModerationStatus
from app.modules.promotions.schemas import ReviewIn
from app.modules.sellers import service
from app.modules.sellers.models import SellerApplication
from app.modules.sellers.schemas import ApplicationOut, ApproveIn, SubscriptionIn, SubscriptionOut
from app.modules.shops.models import Subscription
from app.modules.shops.service import get_shop_or_404
from app.pagination import Page, PageDep

router = APIRouter(prefix="/admin", tags=["admin: sellers"])


@router.get("/seller-applications")
async def list_applications(
    _: AdminUser, session: SessionDep, page: PageDep, status: ModerationStatus | None = None
) -> Page[ApplicationOut]:
    stmt = select(SellerApplication).order_by(SellerApplication.id.desc())
    if status is not None:
        stmt = stmt.where(SellerApplication.status == status)
    items, total = await paginate(session, stmt, page)
    return Page(items=[ApplicationOut.model_validate(a) for a in items], total=total)


@router.post("/seller-applications/{app_id}/approve")
async def approve(
    app_id: int, body: ApproveIn, admin: AdminUser, session: SessionDep
) -> ApplicationOut:
    application = await service.get_application_or_404(session, app_id)
    await service.approve_application(
        session, application, admin, shop_data=body.shop, subscription=body.subscription
    )
    return ApplicationOut.model_validate(application)


@router.post("/seller-applications/{app_id}/reject")
async def reject(
    app_id: int, body: ReviewIn, admin: AdminUser, session: SessionDep
) -> ApplicationOut:
    application = await service.get_application_or_404(session, app_id)
    await service.reject_application(session, application, admin, body.comment)
    return ApplicationOut.model_validate(application)


@router.post("/shops/{shop_id}/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    shop_id: int, body: SubscriptionIn, admin: AdminUser, session: SessionDep
) -> SubscriptionOut:
    shop = await get_shop_or_404(session, shop_id, public=False)
    return SubscriptionOut.model_validate(
        await service.create_subscription(session, shop, body, admin)
    )


@router.get("/shops/{shop_id}/subscriptions")
async def list_subscriptions(
    shop_id: int, _: AdminUser, session: SessionDep
) -> list[SubscriptionOut]:
    await get_shop_or_404(session, shop_id, public=False)
    rows = await session.scalars(
        select(Subscription).where(Subscription.shop_id == shop_id).order_by(Subscription.starts_at)
    )
    return [SubscriptionOut.model_validate(s) for s in rows]
