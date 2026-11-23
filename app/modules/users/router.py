from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.deps import CurrentUser, SessionDep
from app.modules.malls.schemas import MallListItem
from app.modules.shops.schemas import ShopBrief
from app.modules.users import favorites, service
from app.modules.users.schemas import (
    AuthOut,
    OtpRequest,
    OtpVerify,
    RefreshIn,
    TokenPair,
    UserOut,
    UserUpdate,
)
from app.modules.users.sms import SmsSender, get_sms_sender

auth_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(prefix="/me", tags=["me"])


@auth_router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(
    body: OtpRequest, session: SessionDep, sms: Annotated[SmsSender, Depends(get_sms_sender)]
) -> None:
    await service.request_otp(session, body.phone, sms)


@auth_router.post("/otp/verify")
async def verify_otp(body: OtpVerify, session: SessionDep) -> AuthOut:
    user = await service.verify_otp(session, body.phone, body.code)
    tokens = await service.issue_tokens(session, user)
    return AuthOut(**tokens.model_dump(), user=UserOut.model_validate(user))


@auth_router.post("/refresh")
async def refresh(body: RefreshIn, session: SessionDep) -> TokenPair:
    return await service.rotate_refresh(session, body.refresh_token)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, session: SessionDep) -> None:
    await service.revoke_refresh(session, body.refresh_token)


@me_router.get("")
async def get_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@me_router.patch("")
async def patch_me(body: UserUpdate, user: CurrentUser, session: SessionDep) -> UserOut:
    return UserOut.model_validate(await service.update_me(session, user, body))


@me_router.get("/favorites")
async def list_favorites(user: CurrentUser, session: SessionDep) -> list[ShopBrief]:
    return await favorites.list_favorites(session, user)


@me_router.put("/favorites/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(shop_id: int, user: CurrentUser, session: SessionDep) -> None:
    await favorites.add_favorite(session, user, shop_id)


@me_router.delete("/favorites/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(shop_id: int, user: CurrentUser, session: SessionDep) -> None:
    await favorites.remove_favorite(session, user, shop_id)


@me_router.get("/malls")
async def list_my_malls(user: CurrentUser, session: SessionDep) -> list[MallListItem]:
    return await favorites.list_malls(session, user)


@me_router.put("/malls/{mall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_my_mall(mall_id: int, user: CurrentUser, session: SessionDep) -> None:
    await favorites.add_mall(session, user, mall_id)


@me_router.delete("/malls/{mall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_my_mall(mall_id: int, user: CurrentUser, session: SessionDep) -> None:
    await favorites.remove_mall(session, user, mall_id)
