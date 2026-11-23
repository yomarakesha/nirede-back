from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status
from pydantic import BaseModel

from app.deps import AdminUser, SellerUser
from app.storage import Storage, get_storage, save_image

admin_router = APIRouter(prefix="/admin/uploads", tags=["admin: uploads"])
seller_router = APIRouter(prefix="/seller/uploads", tags=["seller"])

StorageDep = Annotated[Storage, Depends(get_storage)]


class UploadOut(BaseModel):
    path: str
    url: str


async def _upload(file: UploadFile, storage: Storage) -> UploadOut:
    path = await save_image(file, storage)
    return UploadOut(path=path, url=storage.url(path))


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def admin_upload(file: UploadFile, _: AdminUser, storage: StorageDep) -> UploadOut:
    return await _upload(file, storage)


@seller_router.post("", status_code=status.HTTP_201_CREATED)
async def seller_upload(file: UploadFile, _: SellerUser, storage: StorageDep) -> UploadOut:
    return await _upload(file, storage)
