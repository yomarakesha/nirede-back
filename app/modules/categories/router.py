from fastapi import APIRouter

from app.deps import SessionDep
from app.modules.categories import service
from app.modules.categories.schemas import CategoryBrief, CategoryNode

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_roots(session: SessionDep) -> list[CategoryBrief]:
    return [
        CategoryBrief.model_validate(n.model_dump()) for n in await service.active_tree(session)
    ]


@router.get("/tree")
async def tree(session: SessionDep) -> list[CategoryNode]:
    return await service.active_tree(session)


@router.get("/{category_id}")
async def get_category(category_id: int, session: SessionDep) -> CategoryNode:
    return await service.public_node(session, category_id)
