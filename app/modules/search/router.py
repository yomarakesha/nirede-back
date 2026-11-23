from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import SessionDep
from app.modules.search import service
from app.modules.search.schemas import SearchOut, SuggestOut

router = APIRouter(prefix="/search", tags=["search"])


def _query(q: str) -> str:
    q = service.normalize_query(q)
    if len(q) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "query_too_short")
    return q


@router.get("/suggest")
async def suggest(
    session: SessionDep, q: Annotated[str, Query(max_length=100)], city_id: int | None = None
) -> SuggestOut:
    return await service.suggest(session, _query(q), city_id)


@router.get("")
async def search(
    session: SessionDep,
    category_id: int | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    city_id: int | None = None,
    mall_id: int | None = None,
) -> SearchOut:
    if (category_id is None) == (q is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "category_id_or_q_required")
    return await service.search(
        session,
        category_id=category_id,
        q=_query(q) if q is not None else None,
        city_id=city_id,
        mall_id=mall_id,
    )
