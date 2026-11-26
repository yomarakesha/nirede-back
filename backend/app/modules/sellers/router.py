from fastapi import APIRouter, status
from sqlalchemy import select

from app.deps import CurrentUser, SellerUser, SessionDep
from app.modules.sellers import service
from app.modules.sellers.models import SellerApplication
from app.modules.sellers.schemas import ApplicationIn, ApplicationOut, SellerShopOut

me_router = APIRouter(prefix="/me/seller-applications", tags=["me"])
seller_router = APIRouter(prefix="/seller", tags=["seller"])


@me_router.post("", status_code=status.HTTP_201_CREATED)
async def submit(body: ApplicationIn, user: CurrentUser, session: SessionDep) -> ApplicationOut:
    return ApplicationOut.model_validate(await service.submit_application(session, user, body))


@me_router.get("")
async def my_applications(user: CurrentUser, session: SessionDep) -> list[ApplicationOut]:
    rows = await session.scalars(
        select(SellerApplication)
        .where(SellerApplication.user_id == user.id)
        .order_by(SellerApplication.id.desc())
    )
    return [ApplicationOut.model_validate(a) for a in rows]


@seller_router.get("/shops")
async def my_shops(user: SellerUser, session: SessionDep) -> list[SellerShopOut]:
    return await service.seller_shops(session, user)
