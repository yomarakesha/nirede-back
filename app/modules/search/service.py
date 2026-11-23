"""Search by category (with its subtree) and by shop name.

The category table is small, so category matching runs in memory over the active tree;
shops are filtered in SQL.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryBrief
from app.modules.malls.models import Mall
from app.modules.malls.service import to_list_items
from app.modules.search.schemas import (
    CategorySuggestion,
    MallCount,
    SearchGroup,
    SearchOut,
    SuggestOut,
)
from app.modules.shops.models import Shop, shop_categories
from app.modules.shops.service import load_briefs, order_premium_first, public_shops

SUGGEST_LIMIT = 5
SIMILARITY_THRESHOLD = 0.3


def normalize_query(q: str) -> str:
    return " ".join(q.lower().split())


@dataclass
class _Node:
    cat: Category
    path: list[Category]
    children: list["_Node"] = field(default_factory=list)

    def subtree_ids(self) -> list[int]:
        ids = [self.cat.id]
        for child in self.children:
            ids.extend(child.subtree_ids())
        return ids

    def text(self, lang: str) -> str:
        names = " ".join(getattr(c, f"name_{lang}") for c in self.path)
        aliases = getattr(self.cat, f"search_aliases_{lang}") or ""
        return f"{names} {aliases}".lower()


async def _active_nodes(session: AsyncSession) -> dict[int, _Node]:
    """Active categories reachable through active parents, with their paths."""
    cats = list(
        await session.scalars(
            select(Category).where(Category.is_active).order_by(Category.sort_order, Category.id)
        )
    )
    by_id = {c.id: c for c in cats}
    nodes: dict[int, _Node] = {}

    def build(cat: Category) -> _Node | None:
        if cat.id in nodes:
            return nodes[cat.id]
        if cat.parent_id is None:
            node = _Node(cat, [cat])
        else:
            parent = by_id.get(cat.parent_id)
            parent_node = build(parent) if parent else None
            if parent_node is None:
                return None
            node = _Node(cat, [*parent_node.path, cat])
            parent_node.children.append(node)
        nodes[cat.id] = node
        return node

    for cat in cats:
        build(cat)
    return nodes


def _shop_filter(stmt, city_id: int | None, mall_id: int | None):
    if city_id is not None:
        stmt = stmt.where(Shop.city_id == city_id)
    if mall_id is not None:
        stmt = stmt.where(Shop.mall_id == mall_id)
    return stmt


def _in_categories(ids: list[int]):
    return Shop.id.in_(
        select(shop_categories.c.shop_id).where(shop_categories.c.category_id.in_(ids))
    )


async def _shop_counts(
    session: AsyncSession, nodes: list[_Node], city_id: int | None
) -> dict[int, int]:
    """Distinct public shops per category subtree."""
    all_ids = {i for n in nodes for i in n.subtree_ids()}
    if not all_ids:
        return {}
    shop_ids = _shop_filter(public_shops(), city_id, None).with_only_columns(Shop.id)
    rows = await session.execute(
        select(shop_categories.c.category_id, shop_categories.c.shop_id).where(
            shop_categories.c.category_id.in_(all_ids), shop_categories.c.shop_id.in_(shop_ids)
        )
    )
    shops_by_cat: dict[int, set[int]] = defaultdict(set)
    for cat_id, shop_id in rows:
        shops_by_cat[cat_id].add(shop_id)
    return {n.cat.id: len(set().union(*(shops_by_cat[i] for i in n.subtree_ids()))) for n in nodes}


def _match_categories(nodes: dict[int, _Node], q: str) -> list[_Node]:
    tokens = q.split()
    return [
        n
        for n in nodes.values()
        if any(all(t in n.text(lang) for t in tokens) for lang in ("ru", "tk"))
    ]


def _rank(matches: list[_Node], q: str, counts: dict[int, int]) -> list[_Node]:
    tokens = q.split()

    def key(n: _Node):
        names = (n.cat.name_ru.lower(), n.cat.name_tk.lower())
        exact = q in names
        own_hits = sum(any(t in name for name in names) for t in tokens)
        return (not exact, -own_hits, -counts.get(n.cat.id, 0), len(n.path), n.cat.id)

    return sorted(matches, key=key)


def _suggestion(node: _Node, count: int) -> CategorySuggestion:
    return CategorySuggestion(
        **CategoryBrief.model_validate(node.cat).model_dump(exclude={"icon_url"}),
        path_ru=[c.name_ru for c in node.path],
        path_tk=[c.name_tk for c in node.path],
        shop_count=count,
    )


async def _top_categories(
    session: AsyncSession, nodes: dict[int, _Node], q: str, city_id: int | None
) -> tuple[list[_Node], dict[int, int]]:
    matches = _match_categories(nodes, q)
    counts = await _shop_counts(session, matches, city_id)
    return _rank(matches, q, counts)[:SUGGEST_LIMIT], counts


async def _malls_for(session: AsyncSession, node: _Node, city_id: int | None) -> list[MallCount]:
    stmt = (
        _shop_filter(public_shops(), city_id, None)
        .where(Shop.mall_id.is_not(None), _in_categories(node.subtree_ids()))
        .with_only_columns(Mall.id, Mall.name_ru, Mall.name_tk, Mall.layout, func.count(Shop.id))
        .group_by(Mall.id)
        .order_by(func.count(Shop.id).desc(), Mall.sort_order, Mall.id)
    )
    return [
        MallCount(mall_id=i, name_ru=ru, name_tk=tk, layout=layout, shop_count=count)
        for i, ru, tk, layout, count in await session.execute(stmt)
    ]


async def suggest(session: AsyncSession, q: str, city_id: int | None) -> SuggestOut:
    q = normalize_query(q)
    nodes = await _active_nodes(session)
    top, counts = await _top_categories(session, nodes, q, city_id)
    malls = await _malls_for(session, top[0], city_id) if top else []

    name = func.lower(Shop.name)
    shops_stmt = _shop_filter(public_shops(), city_id, None).where(
        or_(name.contains(q, autoescape=True), func.similarity(name, q) > SIMILARITY_THRESHOLD)
    )
    shops = list(await session.scalars(order_premium_first(shops_stmt).limit(SUGGEST_LIMIT)))
    return SuggestOut(
        categories=[_suggestion(n, counts.get(n.cat.id, 0)) for n in top],
        malls_for_top_category=malls,
        shops=await load_briefs(session, shops),
    )


async def _similar(
    session: AsyncSession, nodes: dict[int, _Node], q: str, exclude: int | None
) -> list[CategoryBrief]:
    ids = list(nodes)
    if not ids:
        return []
    score = func.greatest(
        func.word_similarity(func.lower(Category.name_ru), q),
        func.word_similarity(func.lower(Category.name_tk), q),
    )
    rows = await session.scalars(
        select(Category.id)
        .where(Category.id.in_(ids), score > SIMILARITY_THRESHOLD)
        .order_by(score.desc(), Category.id)
        .limit(SUGGEST_LIMIT)
    )
    found = list(rows)
    # Parent of the searched category, then the best match and its parent, then the rest.
    result: list[int | None] = [nodes[exclude].cat.parent_id] if exclude is not None else []
    if found:
        result += [found[0], nodes[found[0]].cat.parent_id, *found[1:]]
    unique = [c for c in dict.fromkeys(result) if c in nodes and c != exclude]
    return [CategoryBrief.model_validate(nodes[c].cat) for c in unique[:SUGGEST_LIMIT]]


async def search(
    session: AsyncSession,
    *,
    category_id: int | None,
    q: str | None,
    city_id: int | None,
    mall_id: int | None,
) -> SearchOut:
    nodes = await _active_nodes(session)
    if category_id is not None:
        node = nodes.get(category_id)
        if node is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category_not_found")
        query = normalize_query(node.cat.name_ru)
    else:
        query = normalize_query(q or "")
        top, _ = await _top_categories(session, nodes, query, city_id)
        node = top[0] if top else None

    shops: list[Shop] = []
    if node is not None:
        stmt = _shop_filter(public_shops(), city_id, mall_id).where(
            _in_categories(node.subtree_ids())
        )
        shops = list(await session.scalars(order_premium_first(stmt)))

    briefs = await load_briefs(session, shops)
    by_mall: dict[int | None, list] = defaultdict(list)
    for brief in briefs:
        by_mall[brief.mall.id if brief.mall else None].append(brief)
    mall_ids = [m for m in by_mall if m is not None]
    malls = list(await session.scalars(select(Mall).where(Mall.id.in_(mall_ids))))
    mall_items = {m.id: m for m in await to_list_items(session, malls)}
    sizes = Counter({m: len(v) for m, v in by_mall.items()})
    ordered = sorted(mall_ids, key=lambda m: (-sizes[m], mall_items[m].name_ru))
    groups = [
        SearchGroup(mall=mall_items[m], shop_count=sizes[m], shops=by_mall[m]) for m in ordered
    ]
    if None in by_mall:
        groups.append(SearchGroup(mall=None, shop_count=sizes[None], shops=by_mall[None]))

    similar = []
    if not briefs:
        similar = await _similar(session, nodes, query, node.cat.id if node else None)
    return SearchOut(
        category=CategoryBrief.model_validate(node.cat) if node else None,
        total_shops=len(briefs),
        total_malls=len(mall_ids),
        groups=groups,
        similar_categories=similar,
    )
