from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_or_404
from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryNode


async def get_category_or_404(session: AsyncSession, category_id: int) -> Category:
    return await get_or_404(session, Category, category_id, "category_not_found")


async def subtree_ids(session: AsyncSession, category_id: int) -> list[int]:
    """The category and all its descendants (recursive CTE)."""
    tree = select(Category.id).where(Category.id == category_id).cte(recursive=True)
    tree = tree.union_all(select(Category.id).where(Category.parent_id == tree.c.id))
    return list(await session.scalars(select(tree.c.id)))


async def _all_by_id(session: AsyncSession) -> dict[int, Category]:
    return {c.id: c for c in await session.scalars(select(Category))}


async def ancestors_map(session: AsyncSession, ids: list[int]) -> dict[int, list[Category]]:
    """Path root → self for each id. The category table is small, so it is walked in memory."""
    by_id = await _all_by_id(session)
    result: dict[int, list[Category]] = {}
    for cid in ids:
        path: list[Category] = []
        node = by_id.get(cid)
        while node is not None:
            path.append(node)
            node = by_id.get(node.parent_id) if node.parent_id else None
        result[cid] = list(reversed(path))
    return result


async def active_tree(session: AsyncSession) -> list[CategoryNode]:
    """Active categories as a forest; a node under an inactive parent is hidden."""
    rows = await session.scalars(
        select(Category).where(Category.is_active).order_by(Category.sort_order, Category.id)
    )
    cats = list(rows)
    nodes = {c.id: CategoryNode.model_validate(c) for c in cats}
    roots: list[CategoryNode] = []
    for c in cats:
        if c.parent_id is None:
            roots.append(nodes[c.id])
        elif c.parent_id in nodes:
            nodes[c.parent_id].children.append(nodes[c.id])
    return roots


def _find(nodes: list[CategoryNode], category_id: int) -> CategoryNode | None:
    for node in nodes:
        if node.id == category_id:
            return node
        found = _find(node.children, category_id)
        if found:
            return found
    return None


def _truncate(node: CategoryNode, depth: int) -> CategoryNode:
    children = [] if depth == 0 else [_truncate(c, depth - 1) for c in node.children]
    return node.model_copy(update={"children": children})


async def public_node(session: AsyncSession, category_id: int, depth: int = 2) -> CategoryNode:
    node = _find(await active_tree(session), category_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category_not_found")
    return _truncate(node, depth)


async def check_parent(session: AsyncSession, category: Category | None, parent_id: int) -> None:
    by_id = await _all_by_id(session)
    if parent_id not in by_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category_not_found")
    if category is None:
        return
    node = by_id.get(parent_id)
    while node is not None:
        if node.id == category.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "category_cycle")
        node = by_id.get(node.parent_id) if node.parent_id else None


async def commit_or_slug_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug_taken") from exc
