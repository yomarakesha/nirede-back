"""Small helpers shared by module services."""

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.pagination import PageParams


async def get_or_404[M](
    session: AsyncSession, model: type[M], obj_id: int, detail: str, *, lock: bool = False
) -> M:
    """With `lock`, the row is reloaded under FOR UPDATE: reviews of one row run one at a time."""
    obj = await session.get(model, obj_id, with_for_update=lock, populate_existing=lock)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    return obj


def apply_update(obj: Any, data: BaseModel, *, exclude: set[str] | None = None) -> None:
    for field, value in data.model_dump(exclude_unset=True, exclude=exclude).items():
        setattr(obj, field, value)


async def paginate(session: AsyncSession, stmt: Select, page: PageParams) -> tuple[list, int]:
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return list(rows), total or 0


async def delete_or_409(session: AsyncSession, obj: Any, detail: str) -> None:
    try:
        async with session.begin_nested():
            await session.delete(obj)
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc
    await session.commit()
