# Nirede Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** REST backend for Nirede — a directory telling buyers which shop (mall, floor, number or standalone address) sells a given category, with seller subscriptions and admin moderation.

**Architecture:** FastAPI app split into feature modules under `app/modules/<domain>/` (`models.py`, `schemas.py`, `service.py`, `router.py`, `admin_router.py`). Async SQLAlchemy 2.0 on PostgreSQL 16 with `pg_trgm`; Alembic migrations. Routers are thin; rules live in services. Seller edits go through a `change_requests` table and are applied by the same `update_*` service functions admins use.

**Tech Stack:** Python 3.12+, uv, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.0 + asyncpg, Alembic, PyJWT, python-multipart, Pillow, pytest, pytest-asyncio, httpx, ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-11-23-nirede-backend-design.md`

## Global Constraints

- All user-facing text is a pair of columns/fields `<field>_ru` and `<field>_tk`; responses return both.
- Every table: `id` bigint identity PK, `created_at`, `updated_at` (timestamptz, server defaults).
- All datetimes stored as timestamptz (UTC). Opening hours are `time` in local zone `Asia/Ashgabat`.
- API prefix `/api/v1`. List endpoints take `limit` (1–100, default 20) and `offset` (≥0), return `{"items": [...], "total": int}`.
- Errors use FastAPI `{"detail": ...}`; 404 missing, 403 wrong role/owner, 409 conflict, 422 validation.
- Phones stored E.164 `+993XXXXXXXX` (8 digits after `+993`).
- Roles: `user`, `seller`, `admin`. Languages: `ru`, `tk`.
- Moderation statuses: `pending`, `approved`, `rejected`.
- Premium is never stored: shop is premium iff it has a subscription with `starts_at <= now < ends_at`.
- Default subscription: 30 days, amount 30 TMT.
- JWT access 30 min, refresh 30 days (stored as sha256 hash). OTP: 4 digits, TTL 5 min, max 5 verify attempts, request rate 1/min and 5/hour per phone.
- Uploads: jpeg/png/webp, max 5 MB, resized to max 1600 px side, served under `/media`.
- SMS and push are interfaces with logging stubs only.
- Search never hides non-premium shops; premium only reorders (premium first, then name).
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Mixed-case and Turkmen letters in search (`"ýüpek"`, `"ПАЛЬТО"`) — must match `Ýüpek` / `Пальто`. Test in Task 9.
2. Opening hours past midnight (`opens_at=10:00`, `closes_at=02:00`) — `is_open_now` true at 01:00 local. Test in Task 1.
3. Phone typed with spaces or local prefix (`"+993 65 12 34 56"`, `"865123456"`, `"65123456"`) — same user. Test in Task 2.
4. Approving a change request after the shop's subscription expired or the shop was deleted — auto-reject, live shop unchanged. Test in Task 13.
5. A user who both favorited a shop and has its mall in "my malls" — gets exactly one notification per promotion. Test in Task 11.

---

## File Structure

```
pyproject.toml, docker-compose.yml, Dockerfile, .env.example, alembic.ini, README.md
alembic/env.py, alembic/versions/*
app/main.py            app factory, router mounting, /media static, /health
app/config.py          Settings
app/db.py              Base, TimestampMixin, engine, session factory, get_session
app/deps.py            SessionDep, CurrentUser, OptionalUser, AdminUser, SellerUser
app/pagination.py      Page[T], PageParams
app/security.py        JWT + hashing + OTP generation
app/phone.py           normalize_phone
app/timeutil.py        utcnow, is_open
app/storage.py         Storage protocol, LocalStorage, get_storage, save_image
app/i18n.py            I18nField helpers (shared Pydantic mixins)
app/cli.py             create-admin
app/modules/users/         User, OtpCode, RefreshToken, favorites, user_malls, auth + me
app/modules/cities/
app/modules/malls/         Mall, MallPhoto, MallFloor
app/modules/categories/
app/modules/shops/         Shop, ShopPhoto, shop_categories, Subscription
app/modules/search/
app/modules/promotions/
app/modules/notifications/ Notification, DeviceToken, PushSender
app/modules/sellers/       SellerApplication, subscriptions admin, seller routes
app/modules/moderation/    ChangeRequest
tests/conftest.py, tests/factories.py, tests/<module>/test_*.py
```

`app/models.py` imports every module's models so Alembic and `create_all` see them.

---

### Task 1: Project scaffold, DB, test harness, utilities

**Files:**
- Create: `pyproject.toml`, `docker-compose.yml`, `Dockerfile`, `.env.example`, `.gitignore`, `alembic.ini`, `alembic/env.py`, `app/__init__.py`, `app/main.py`, `app/config.py`, `app/db.py`, `app/deps.py`, `app/pagination.py`, `app/timeutil.py`, `app/models.py`, `tests/conftest.py`
- Test: `tests/test_health.py`, `tests/test_timeutil.py`

**Interfaces:**
- Produces:
  - `Settings` fields: `database_url: str`, `test_database_url: str`, `jwt_secret: str`, `access_ttl_minutes=30`, `refresh_ttl_days=30`, `otp_ttl_minutes=5`, `otp_max_attempts=5`, `media_dir: Path = Path("media")`, `media_url="/media"`, `timezone="Asia/Ashgabat"`; `get_settings() -> Settings` (lru_cache).
  - `Base(DeclarativeBase)`; `TimestampMixin` with `id: Mapped[int]` (BigInteger identity), `created_at`, `updated_at`.
  - `get_session() -> AsyncIterator[AsyncSession]`; `SessionDep = Annotated[AsyncSession, Depends(get_session)]`.
  - `Page[T](BaseModel)`: `items: list[T]`, `total: int`; `PageParams` dependency with `limit`, `offset`; `PageDep`.
  - `utcnow() -> datetime` (aware UTC); `is_open(opens_at: time | None, closes_at: time | None, at: datetime) -> bool` (converts `at` to `Asia/Ashgabat`; `None` hours → False; `closes_at <= opens_at` means overnight).
  - `create_app() -> FastAPI`; `app = create_app()`.
  - Test fixtures: `session` (AsyncSession bound to one connection inside an outer transaction, `join_transaction_mode="create_savepoint"`, rolled back after test), `client` (`httpx.AsyncClient` with `ASGITransport`, `get_session` overridden to yield `session`).

- [ ] **Step 1: Init repo and project**

`git init`; `uv init --app --name nirede`; add deps: `fastapi uvicorn[standard] pydantic-settings sqlalchemy[asyncio] asyncpg alembic pyjwt python-multipart pillow`; dev deps: `pytest pytest-asyncio httpx ruff`. `pyproject.toml`: `[tool.pytest.ini_options] asyncio_mode="auto"`, `asyncio_default_fixture_loop_scope="session"`, `asyncio_default_test_loop_scope="session"`; ruff line-length 100, select `E,F,I,UP,B`.

- [ ] **Step 2: Compose + env**

`docker-compose.yml`: service `db` = `postgres:16`, port `5433:5432`, user/password/db `nirede`, init script creating `nirede_test`; service `api` builds `Dockerfile`, runs `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0`. `.env.example` with `DATABASE_URL=postgresql+asyncpg://nirede:nirede@localhost:5433/nirede`, `TEST_DATABASE_URL=...nirede_test`, `JWT_SECRET=change-me`. Run `docker compose up -d db`.

- [ ] **Step 3: Write failing tests**

```python
# tests/test_health.py
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

# tests/test_timeutil.py
from datetime import datetime, time, timezone
from app.timeutil import is_open

def _local(h, m=0):  # Asia/Ashgabat is UTC+5
    return datetime(2026, 11, 23, (h - 5) % 24, m, tzinfo=timezone.utc)

def test_open_during_day():
    assert is_open(time(10), time(22), _local(12))

def test_closed_after_close():
    assert not is_open(time(10), time(22), _local(22, 30))

def test_overnight_open_after_midnight():
    assert is_open(time(10), time(2), _local(1))

def test_overnight_closed_morning():
    assert not is_open(time(10), time(2), _local(9))

def test_missing_hours_closed():
    assert not is_open(None, None, _local(12))
```

- [ ] **Step 4: Run, expect FAIL** — `uv run pytest -q` → import errors.

- [ ] **Step 5: Implement** config, db, deps, pagination, timeutil, `create_app` with `GET /health`, `app/models.py` (empty imports for now), `conftest.py` (session-scoped engine on `TEST_DATABASE_URL`; at session start `CREATE EXTENSION IF NOT EXISTS pg_trgm`, `drop_all` + `create_all` from `Base.metadata` after importing `app.models`).

- [ ] **Step 6: Alembic** — `alembic init -t async alembic`; `env.py` reads `get_settings().database_url`, `target_metadata = Base.metadata`, imports `app.models`. First migration created empty with `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")`.

- [ ] **Step 7: Run, expect PASS** — `uv run pytest -q`; `uv run ruff check .`

- [ ] **Step 8: Commit** — `git add -A && git commit -m "chore: scaffold FastAPI project with async DB and test harness"`

---

### Task 2: Users, phone OTP auth, roles, admin CLI

**Files:**
- Create: `app/phone.py`, `app/security.py`, `app/cli.py`, `app/modules/users/{__init__,models,schemas,service,sms,router}.py`
- Modify: `app/deps.py`, `app/main.py`, `app/models.py`
- Test: `tests/test_phone.py`, `tests/users/test_auth.py`, `tests/users/test_me.py`, `tests/factories.py`

**Interfaces:**
- Consumes: `SessionDep`, `TimestampMixin`, `utcnow`, `get_settings`.
- Produces:
  - `normalize_phone(raw: str) -> str` → `"+993XXXXXXXX"`; accepts spaces/dashes/parentheses, prefixes `+993`, `993`, `8`, or bare 8 digits; else `ValueError`.
  - Enums `UserRole(StrEnum)`: `user|seller|admin`; `Language(StrEnum)`: `ru|tk`; `ModerationStatus(StrEnum)`: `pending|approved|rejected` (put in `app/enums.py`, shared).
  - `User`: `phone` unique, `name: str | None`, `role`, `language` default `ru`, `notify_favorite_shops=True`, `notify_my_malls=True`.
  - `OtpCode`: `phone`, `code_hash`, `expires_at`, `attempts`. `RefreshToken`: `user_id`, `token_hash` unique, `expires_at`, `revoked_at`.
  - `create_access_token(user_id: int, role: str) -> str`; `decode_access_token(token: str) -> int` (user id; raises `HTTPException(401)`); `hash_token(raw: str) -> str` (sha256 hex); `generate_otp() -> str` (4 digits, `secrets`).
  - `SmsSender` Protocol `async def send(self, phone: str, text: str) -> None`; `LoggingSmsSender`; `get_sms_sender()` dependency.
  - Service: `request_otp(session, phone, sms) -> None` (409 with detail `"otp_rate_limited"` when over 1/min or 5/hour); `verify_otp(session, phone, code) -> User` (401 `"otp_invalid"`, increments attempts, 401 `"otp_expired"` past TTL or attempts ≥ 5; creates user on first login); `issue_tokens(session, user) -> TokenPair`; `rotate_refresh(session, raw) -> TokenPair`; `revoke_refresh(session, raw)`.
  - Deps: `CurrentUser` (401 without valid bearer), `OptionalUser`, `require_role(*roles)`; `AdminUser = Annotated[User, Depends(require_role("admin"))]`, `SellerUser` = role `seller` or `admin`.
  - Routes: `POST /api/v1/auth/otp/request {phone}` → 204; `POST /auth/otp/verify {phone, code}` → `{access_token, refresh_token, user: UserOut}`; `POST /auth/refresh {refresh_token}`; `POST /auth/logout {refresh_token}` → 204; `GET /me`; `PATCH /me {name?, language?, notify_favorite_shops?, notify_my_malls?}`.
  - `UserOut`: `id, phone, name, role, language, notify_favorite_shops, notify_my_malls`.
  - Test factories in `tests/factories.py`: `async def make_user(session, phone="+99365123456", role="user") -> User`; `def auth_headers(user) -> dict` (bearer from `create_access_token`).
  - CLI: `python -m app.cli create-admin <phone>` creates or promotes user to `admin`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_phone.py
import pytest
from app.phone import normalize_phone

@pytest.mark.parametrize("raw", ["+993 65 12 34 56", "+99365123456", "99365123456",
                                 "865123456", "65123456", "+993 (65) 12-34-56"])
def test_normalize(raw):
    assert normalize_phone(raw) == "+99365123456"

@pytest.mark.parametrize("raw", ["", "123", "+7 999 123 45 67", "abc"])
def test_reject(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)
```

`tests/users/test_auth.py` (monkeypatch `generate_otp` to return `"1234"`, override `get_sms_sender` with a list-collecting fake):
- `test_otp_login_creates_user`: request → verify `"1234"` → 200, `user.phone == "+99365123456"`, `role == "user"`, SMS fake got 1 message containing `"1234"`.
- `test_same_user_for_phone_variants`: login with `"+993 65 12 34 56"` then `"865123456"` → same `user.id`.
- `test_wrong_code_then_lockout`: 5 wrong verifies → 401; 6th with correct code → 401 `"otp_expired"`.
- `test_rate_limit`: two requests within a minute → second 409 `"otp_rate_limited"`.
- `test_refresh_rotates`: refresh returns new pair; old refresh token reused → 401.
- `test_logout_revokes`: logout then refresh → 401.

`tests/users/test_me.py`:
- `test_me_requires_auth` → 401.
- `test_patch_me`: PATCH `{"name": "Аман", "language": "tk", "notify_my_malls": false}` → reflected in `GET /me`.
- `test_patch_me_cannot_change_role`: PATCH `{"role": "admin"}` → role stays `user` (extra fields forbidden → 422).

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement** phone, security, enums, users module, deps, CLI; mount router in `create_app`.
- [ ] **Step 4: Alembic revision** — `uv run alembic revision --autogenerate -m "users"`; review file.
- [ ] **Step 5: Run, expect PASS** — `uv run pytest -q`
- [ ] **Step 6: Commit** — `feat: phone OTP auth, users, roles`

---

### Task 3: Cities

**Files:**
- Create: `app/modules/cities/{__init__,models,schemas,service,router,admin_router}.py`
- Test: `tests/cities/test_cities.py`

**Interfaces:**
- Consumes: `AdminUser`, `SessionDep`, `Page`, `PageDep`.
- Produces: `City`: `name_ru`, `name_tk`, `is_active=True`. Schemas `CityCreate`, `CityUpdate` (all optional), `CityOut`. `get_city_or_404(session, city_id) -> City`. Routes: `GET /api/v1/cities` (active only, no pagination); `/api/v1/admin/cities` GET (paged, includes inactive), POST, GET `/{id}`, PATCH `/{id}`, DELETE `/{id}` (409 `"city_in_use"` if malls/shops reference it — FK `RESTRICT`, catch `IntegrityError`).

- [ ] **Step 1: Failing tests** — `test_admin_crud_city` (create `{"name_ru":"Ашхабад","name_tk":"Aşgabat"}` → 201, patch, list total 1, delete → 204); `test_public_lists_only_active`; `test_non_admin_forbidden` (user token → 403, no token → 401).
- [ ] **Step 2: Run, FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Autogenerate migration, run tests, PASS**
- [ ] **Step 5: Commit** — `feat: cities CRUD`

---

### Task 4: Storage and uploads

**Files:**
- Create: `app/storage.py`, `app/modules/uploads/{__init__,router}.py`
- Modify: `app/main.py` (mount `StaticFiles` at `settings.media_url`)
- Test: `tests/test_uploads.py`

**Interfaces:**
- Produces:
  - `Storage` Protocol: `async def save(self, data: bytes, ext: str) -> str` (returns relative path like `"2026/11/<uuid>.webp"`); `def url(self, path: str) -> str`.
  - `LocalStorage(root: Path, base_url: str)`; `get_storage() -> Storage`.
  - `async def save_image(file: UploadFile, storage: Storage) -> str` — validates content type `image/jpeg|png|webp` and size ≤ 5 MB (422 `"invalid_image"` / `"image_too_large"`), opens with Pillow, downscales to max 1600 px, saves as webp.
  - Routes: `POST /api/v1/admin/uploads` (AdminUser) and `POST /api/v1/seller/uploads` (SellerUser), multipart field `file` → `{"path": str, "url": str}`.
  - Image fields in all later models store the relative `path`; Out schemas expose `<field>_url` computed via `storage.url`.

- [ ] **Step 1: Failing tests** (override `get_storage` with `LocalStorage(tmp_path, "/media")`): `test_upload_png_returns_webp_path` (2000×1000 PNG → path ends `.webp`, saved file width 1600); `test_reject_non_image` (text/plain → 422); `test_reject_too_large` (6 MB → 422); `test_user_cannot_upload` (403).
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: PASS**
- [ ] **Step 5: Commit** — `feat: image storage and uploads`

---

### Task 5: Malls

**Files:**
- Create: `app/modules/malls/{__init__,models,schemas,service,router,admin_router}.py`
- Test: `tests/malls/test_malls.py`

**Interfaces:**
- Consumes: `City`, `get_city_or_404`, `Storage`.
- Produces:
  - `MallLayout(StrEnum)`: `floors|rows`.
  - `Mall`: `city_id` FK RESTRICT, `name_*`, `address_*`, `description_*` nullable, `phone` nullable, `opens_at`/`closes_at` time nullable, `layout`, `floors_count` nullable, `is_active`, `sort_order=0`; relationships `photos` (ordered by `position`), `floors` (ordered by `number`).
  - `MallPhoto`: `mall_id` CASCADE, `path`, `position`. `MallFloor`: `mall_id` CASCADE, `number: int`, `label_ru/label_tk` nullable (e.g. "Ряды 13–24"), `summary_ru/summary_tk`; unique `(mall_id, number)`.
  - `get_mall_or_404(session, mall_id) -> Mall`.
  - Schemas: `MallCreate`, `MallUpdate`, `MallListItem` (`id, name_*, address_*, layout, floors_count, opens_at, closes_at, cover_url`), `MallDetail` (+ `phone, description_*, photos: list[PhotoOut], floors: list[MallFloorOut], is_open_now, shop_count, root_categories: list[CategoryBrief]`).
  - Routes: `GET /api/v1/malls?city_id=` (active, ordered `sort_order, id`); `GET /malls/{id}` (`shop_count` and `root_categories` are 0/[] until Task 7 fills them — add the query in Task 7). Admin: CRUD `/admin/malls`; `PUT /admin/malls/{id}/photos {paths: list[str]}` replaces photos in given order; `PUT /admin/malls/{id}/floors [{number, label_*, summary_*}]` replaces floors.
  - Validation: `layout="floors"` requires `floors_count >= 1` (422).

- [ ] **Step 1: Failing tests** — admin CRUD; `test_floors_layout_requires_floors_count` (422); `test_replace_photos_keeps_order`; `test_public_detail` (photos + floors sorted, `is_open_now` present); `test_filter_by_city`; `test_delete_city_with_mall_conflict` (409 `"city_in_use"`).
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: malls with photos and floors`

---

### Task 6: Categories tree

**Files:**
- Create: `app/modules/categories/{__init__,models,schemas,service,router,admin_router}.py`
- Test: `tests/categories/test_categories.py`

**Interfaces:**
- Produces:
  - `Category`: `parent_id` self FK RESTRICT nullable, `name_*`, `slug` unique, `icon` nullable, `search_aliases_ru/tk` text nullable, `sort_order=0`, `is_active`. Trigram GIN indexes on `lower(name_ru)`, `lower(name_tk)` (declare via `Index(..., postgresql_using="gin", postgresql_ops={...: "gin_trgm_ops"})`).
  - `async def subtree_ids(session, category_id: int) -> list[int]` (recursive CTE, includes self).
  - `async def ancestors_map(session, ids: list[int]) -> dict[int, list[Category]]` (root → self path for each id).
  - Schemas: `CategoryBrief` (`id, name_*, icon_url, slug`), `CategoryNode` (`CategoryBrief` + `children: list[CategoryNode]`), `CategoryCreate`, `CategoryUpdate`.
  - Routes: `GET /api/v1/categories` (active roots); `GET /categories/{id}` (node with 2 levels of active children); `GET /categories/tree` (full active tree). Admin CRUD `/admin/categories`; PATCH rejects setting `parent_id` to self or a descendant (422 `"category_cycle"`); DELETE with children or shops → 409 `"category_in_use"`.

- [ ] **Step 1: Failing tests** — build Женщинам › Верхняя одежда › Пальто: `test_subtree_ids` (root → 3 ids), `test_ancestors_map` (Пальто path names `["Женщинам","Верхняя одежда","Пальто"]`), `test_detail_two_levels`, `test_cycle_rejected`, `test_delete_with_children_conflict`, `test_inactive_hidden_publicly`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: category tree`

---

### Task 7: Shops, photos, categories link, subscriptions model, premium

**Files:**
- Create: `app/modules/shops/{__init__,models,schemas,service,router,admin_router}.py`
- Modify: `app/modules/malls/service.py` (fill `shop_count`, `root_categories`, add `GET /malls/{id}/shops`)
- Test: `tests/shops/test_shops.py`, `tests/malls/test_mall_shops.py`

**Interfaces:**
- Consumes: `Mall`, `City`, `Category`, `subtree_ids`, `ancestors_map`, `is_open`, `utcnow`.
- Produces:
  - `Shop`: `name`, `logo` nullable, `phone` nullable, `opens_at/closes_at` nullable, `how_to_find_ru/tk` nullable, `is_active`, `city_id` FK RESTRICT not null, `mall_id` FK RESTRICT nullable, `floor: int | None`, `row: str | None`, `number: str | None`, `address_ru/tk` nullable, `owner_id` FK users SET NULL nullable. Trigram GIN index on `lower(name)`.
  - DB `CHECK ck_shop_location`: `(mall_id IS NOT NULL AND number IS NOT NULL AND address_ru IS NULL AND address_tk IS NULL) OR (mall_id IS NULL AND address_ru IS NOT NULL AND floor IS NULL AND row IS NULL AND number IS NULL)`.
  - `ShopPhoto` (`shop_id` CASCADE, `path`, `position`); `shop_categories` table (`shop_id` CASCADE, `category_id` RESTRICT, PK both).
  - `Subscription`: `shop_id` CASCADE, `starts_at`, `ends_at`, `amount: Decimal` (Numeric(10,2)), `activated_by` FK users SET NULL, `note` nullable.
  - `def premium_clause(now: datetime)` → SQL boolean expression `EXISTS(subscription active for Shop.id)`; reused in search and listings.
  - Schemas: `ShopLocation` (`mall_id, floor, row, number, city_id, address_ru, address_tk`), `ShopCreate` (`name, logo, phone, opens_at, closes_at, how_to_find_*, location fields flattened, category_ids: list[int], photos: list[str]`), `ShopUpdate` (same, all optional), `ShopBrief` (`id, name, logo_url, mall: MallRef | None` (`id, name_*, layout`), `floor, row, number, address_*, is_premium, categories: list[CategoryBrief]` (max 3, for the "Пальто, пуховики, платья" line)), `ShopDetail` (`ShopBrief` + `phone, how_to_find_*, photos, is_open_now, opens_at, closes_at, all categories`).
  - Service: `create_shop(session, data: ShopCreate) -> Shop`; `update_shop(session, shop: Shop, data: ShopUpdate) -> Shop` — both validate: mall exists and is active; in-mall shop gets `city_id = mall.city_id`; `floors` mall requires `floor` in `1..floors_count` and `row is None`; `rows` mall requires `row` and `floor is None`; standalone requires `city_id` and `address_ru`; all category ids exist (422 detail names the problem: `"floor_required"`, `"row_required"`, `"floor_out_of_range"`, `"unknown_category"`, …). `get_shop_or_404(session, shop_id, *, public: bool)`; `load_briefs(session, shops) -> list[ShopBrief]` (batch premium + categories).
  - Routes: `GET /api/v1/shops/{id}` (active only → `ShopDetail`); `GET /malls/{id}/shops?floor=&row=&category_id=` → `{total, items: list[ShopBrief]}`, premium first then name, `category_id` matches subtree. Admin: CRUD `/admin/shops` (list filters `mall_id`, `city_id`, `q`).
  - `MallDetail.shop_count` = active shops in mall; `root_categories` = distinct roots of categories linked to those shops.

- [ ] **Step 1: Failing tests**
  - `test_create_in_mall_shop_sets_city` (shop city = mall city even if a different `city_id` is sent).
  - `test_floor_required_for_floors_mall`, `test_row_required_for_rows_mall`, `test_floor_out_of_range` (422 with exact details).
  - `test_standalone_requires_address`.
  - `test_check_constraint_blocks_mixed_location` — direct ORM insert with both `mall_id` and `address_ru` → `IntegrityError`.
  - `test_shop_detail_premium` — no subscription → `is_premium` false; add subscription `now-1d..now+29d` → true; expired one → false.
  - `test_mall_shops_premium_first` — shops "Elegant", "Moda Line"(premium), "Lady Style"(premium) on floor 2 → order `["Lady Style","Moda Line","Elegant"]`.
  - `test_mall_shops_category_subtree` — shop linked to Пальто is returned for `category_id=Женщинам`.
  - `test_mall_detail_counts` — `shop_count` and `root_categories`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: shops, subscriptions model, premium ordering`

---

### Task 8: Favorites and "my malls"

**Files:**
- Modify: `app/modules/users/models.py` (association tables), `app/modules/users/router.py`
- Create: `app/modules/users/favorites.py` (service functions)
- Test: `tests/users/test_favorites.py`

**Interfaces:**
- Produces: tables `favorite_shops(user_id, shop_id)` and `user_malls(user_id, mall_id)`, PK both, CASCADE both sides, `created_at`. Routes: `GET /api/v1/me/favorites` → `list[ShopBrief]` (newest first); `PUT /me/favorites/{shop_id}` → 204 idempotent (404 unknown/inactive shop); `DELETE` → 204 idempotent. Same trio for `/me/malls/{mall_id}` returning `list[MallListItem]`. `ShopDetail` and `MallDetail` gain `is_saved: bool` (false for anonymous; uses `OptionalUser`).

- [ ] **Step 1: Failing tests** — `test_add_list_remove_favorite`, `test_put_twice_idempotent`, `test_is_saved_flag`, `test_my_malls_roundtrip`, `test_requires_auth`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: favorites and my malls`

---

### Task 9: Search

**Files:**
- Create: `app/modules/search/{__init__,schemas,service,router}.py`
- Test: `tests/search/test_suggest.py`, `tests/search/test_search.py`, `tests/search/conftest.py` (seed fixture mirroring Figma data)

**Interfaces:**
- Consumes: `Category`, `subtree_ids`, `ancestors_map`, `Shop`, `premium_clause`, `load_briefs`, `Mall`.
- Produces:
  - `normalize_query(q: str) -> str` (strip, lowercase, collapse whitespace).
  - Category match rule: tokens of the query; a category matches when every token is a substring (case-insensitive, `lower()` in SQL) of the concatenation of its path names + its aliases, in either language; ranking = `similarity(lower(name), q)` desc, then fewer path levels. Do it in SQL: recursive CTE producing `(id, path_text_ru, path_text_tk)` for active categories, then filter with `ILIKE ALL` on token patterns. Category limit 5.
  - `GET /api/v1/search/suggest?q=&city_id=` → `{categories: [{id, name_ru, name_tk, path_ru: list[str], path_tk: list[str], shop_count}], malls_for_top_category: [{mall_id, name_ru, name_tk, layout, shop_count}], shops: list[ShopBrief]}`; `q` min length 2 (422); shops match `lower(name)` substring or trigram similarity > 0.3, limit 5, premium first.
  - `GET /api/v1/search?category_id=&q=&city_id=&mall_id=` (exactly one of `category_id`/`q` required, 422 otherwise; with `q`, use the top matched category) → `{category: CategoryBrief | None, total_shops, total_malls, groups: [{mall: MallListItem | None, shop_count, shops: list[ShopBrief]}], similar_categories: list[CategoryBrief]}`. Groups ordered by `shop_count` desc; the standalone group (`mall=None`) last. Inside a group premium first, then name. `similar_categories` filled only when `total_shops == 0`: up to 5 categories with best `similarity` to the query on names, plus parent of the best match, deduplicated.
  - `shop_count` everywhere = distinct active shops linked to the category subtree (and city if given).

- [ ] **Step 1: Seed fixture** — city Ашхабад; malls Беркарар (floors 4), Аркач (floors 3), Ашхабад Молл (floors 4), Толкучка (rows); categories Женщинам › Верхняя одежда › Пальто (alias_ru "женское пальто женские пальто"), Мужчинам › Верхняя одежда › Пальто, Детям › Верхняя одежда › Шубы; shops: Беркарар — Moda Line (premium, f2 №214), Lady Style (premium, f2 №217), Palto House (f1 №116), Elegant (f2 №216); Аркач — Zamana (f1 №24); Толкучка — Ýüpek (row 14, №32); one standalone shop "Город Пальто" with address; all linked to women's Пальто.

- [ ] **Step 2: Failing tests**
  - `test_suggest_paltO_lists_three_categories` — `q="пальто"` → categories include women's and men's Пальто with `path_ru == ["Женщинам","Верхняя одежда","Пальто"]`, women's `shop_count == 7`.
  - `test_suggest_malls_for_top_category` — Беркарар 4, Аркач 1, Толкучка 1 (standalone excluded).
  - `test_suggest_phrase_women` — `q="женское пальто"` → top category is women's Пальто.
  - `test_suggest_case_and_turkmen_letters` — `q="ýüpek"` and `q="ÝÜPEK"` → shops contain Ýüpek; `q="ПАЛЬТО"` same as `"пальто"`.
  - `test_search_groups` — `category_id=women Пальто` → `total_shops == 7`, `total_malls == 3`, first group Беркарар with names `["Lady Style","Moda Line","Elegant","Palto House"]`, last group `mall is None`.
  - `test_search_by_q_uses_top_category`.
  - `test_search_mall_filter` — `mall_id=Аркач` → one group.
  - `test_empty_result_similar_categories` — `q="детская норковая шуба"` → `total_shops == 0`, `similar_categories` contains "Шубы" and its parent "Верхняя одежда".
  - `test_inactive_shop_hidden`.
  - `test_q_too_short_422`.
- [ ] **Step 3: FAIL** · **Step 4: Implement** · **Step 5: PASS**
- [ ] **Step 6: Commit** — `feat: search suggest and grouped results`

---

### Task 10: Promotions (public + admin)

**Files:**
- Create: `app/modules/promotions/{__init__,models,schemas,service,router,admin_router}.py`
- Test: `tests/promotions/test_promotions.py`

**Interfaces:**
- Consumes: `Shop`, `premium_clause`, `ShopBrief`, `ModerationStatus`.
- Produces:
  - `Promotion`: `shop_id` CASCADE, `title_*`, `badge` (str ≤ 16), `description_*` nullable, `image` nullable, `starts_at`, `ends_at` (`CHECK ends_at > starts_at`), `status` default `pending`, `created_by` FK users SET NULL, `admin_comment` nullable.
  - `active_clause(now)` = `status == approved AND starts_at <= now AND ends_at > now`.
  - Schemas `PromotionCreate` (`shop_id, title_*, badge, description_*, image, starts_at, ends_at`), `PromotionUpdate` (all optional except `shop_id` not changeable), `PromotionOut` (`id, title_*, badge, description_*, image_url, starts_at, ends_at, status, shop: ShopBrief`).
  - Service: `create_promotion(session, data, author, *, approved: bool) -> Promotion`; `update_promotion(session, promo, data: PromotionUpdate) -> Promotion`; `set_status(session, promo, status, comment=None) -> bool` returns True when promotion became publicly active by this call (used to trigger notifications in Task 11).
  - Routes: `GET /api/v1/promotions?city_id=&mall_id=` → `{featured: PromotionOut | None, items: list[PromotionOut]}` (active only; `featured` = newest-`starts_at` active promotion of a premium shop, excluded from `items`; `items` ordered `ends_at` asc). Admin: CRUD `/admin/promotions` (admin-created → `approved`), `GET /admin/promotions?status=`, `POST /admin/promotions/{id}/approve`, `POST /admin/promotions/{id}/reject {comment}`.

- [ ] **Step 1: Failing tests** — `test_admin_created_is_public`; `test_pending_not_public`; `test_expired_and_future_hidden`; `test_featured_is_premium_shop_promo`; `test_filter_by_mall`; `test_ends_before_starts_422`; `test_approve_then_public`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: promotions`

---

### Task 11: Notifications, device tokens, push stub

**Files:**
- Create: `app/modules/notifications/{__init__,models,schemas,service,push,router}.py`
- Modify: `app/modules/promotions/admin_router.py` (call notifications after approve/create)
- Test: `tests/notifications/test_notifications.py`

**Interfaces:**
- Consumes: `Promotion`, `set_status`, `favorite_shops`, `user_malls`, `User`.
- Produces:
  - `Notification`: `user_id` CASCADE, `promotion_id` SET NULL nullable, `title_*`, `body_*`, `image` nullable, `read_at` nullable; index `(user_id, created_at desc)`.
  - `DeviceToken`: `user_id` CASCADE, `token` unique, `platform` (`ios|android`).
  - `PushSender` Protocol `async def send(self, tokens: list[str], title: str, body: str, data: dict) -> None`; `LoggingPushSender`; `get_push_sender()`.
  - `async def notify_promotion_published(session, promotion: Promotion) -> list[Notification]` — recipients = (users with `notify_favorite_shops` who favorited the shop) ∪ (users with `notify_my_malls` whose `user_malls` contains `shop.mall_id`), distinct; only if promotion is active now (future-dated promotions get no notification — spec non-goal for scheduling). Title: `"{mall.name_ru}"` / `"{mall.name_tk}"` (or shop name for standalone); body: `"{shop.name}: {promotion.title_ru}"` / tk.
  - `async def push_notifications(notifications, push: PushSender, session_factory)` — run as `BackgroundTasks`; sends in recipient's `language`.
  - Routes: `GET /api/v1/me/notifications` (paged, newest first); `GET /me/notifications/unread-count` → `{count}`; `POST /me/notifications/{id}/read` → 204 (404 if not own); `POST /me/notifications/read-all` → 204; `POST /me/devices {token, platform}` → 204 upsert (token moves to current user); `DELETE /me/devices/{token}` → 204.

- [ ] **Step 1: Failing tests**
  - `test_fanout_favorites_and_malls` — u1 favorited shop, u2 has mall, u3 neither → u1, u2 notified.
  - `test_user_with_both_gets_one` — favorited + mall → exactly 1 notification.
  - `test_respects_toggles` — `notify_favorite_shops=False` user not notified via favorites.
  - `test_future_promotion_no_notification`.
  - `test_admin_approve_triggers_notification` (through API; fake push records one call with the user's device token).
  - `test_feed_read_flow` — unread-count 2 → read one → 1 → read-all → 0; reading someone else's → 404.
  - `test_device_token_moves_between_users`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: notifications and push stub`

---

### Task 12: Seller applications and subscriptions

**Files:**
- Create: `app/modules/sellers/{__init__,models,schemas,service,router,admin_router}.py`
- Test: `tests/sellers/test_applications.py`, `tests/sellers/test_subscriptions.py`

**Interfaces:**
- Consumes: `create_shop`, `ShopCreate`, `Subscription`, `User`, `normalize_phone`.
- Produces:
  - `SellerApplication`: `user_id` CASCADE, `shop_id` SET NULL nullable, `shop_name`, `mall_id` nullable, `floor`, `row`, `number`, `city_id` nullable, `address` nullable, `contact_phone`, `status` default `pending`, `admin_comment`, `reviewed_by`, `reviewed_at`.
  - `async def create_subscription(session, shop: Shop, *, amount: Decimal = Decimal("30"), days: int = 30, admin: User) -> Subscription` — `starts_at = max(now, latest ends_at of shop)`.
  - `async def has_active_subscription(session, shop_id: int) -> bool`.
  - `async def approve_application(session, application, admin, *, shop_data: ShopCreate | None, subscription: SubscriptionIn | None) -> Shop` — one transaction: if `application.shop_id` is null, `shop_data` is required (422 `"shop_data_required"`; admin fills categories etc.) and `create_shop` is called; sets `shop.owner_id`, user role → `seller` (admin stays admin); creates subscription if given. 409 `"shop_already_owned"` when shop has another owner. 409 `"already_reviewed"` for non-pending.
  - Routes: `POST /api/v1/me/seller-applications` (one pending per user → 409 `"application_pending"`; `shop_id` must exist when given) and `GET /me/seller-applications`. Admin: `GET /admin/seller-applications?status=`, `POST /admin/seller-applications/{id}/approve {shop: ShopCreate | null, subscription: {amount, days} | null}`, `POST /.../reject {comment}`; `POST /admin/shops/{id}/subscriptions {amount=30, days=30, note?}`, `GET /admin/shops/{id}/subscriptions`.
  - `GET /api/v1/seller/shops` (SellerUser) → own shops: `ShopBrief` + `subscription_ends_at`, `pending_change_requests: int` (0 until Task 13).
  - Admin users: `GET /api/v1/admin/users?role=&q=` (paged, `q` matches phone/name) and `PATCH /admin/users/{id} {role}` (admin cannot demote self → 409 `"cannot_demote_self"`).

- [ ] **Step 1: Failing tests** — `test_claim_existing_shop_flow` (apply with `shop_id` → admin approves with subscription → user role `seller`, owner set, shop `is_premium`); `test_new_shop_flow_requires_shop_data`; `test_one_pending_application`; `test_shop_already_owned_conflict`; `test_reject_sets_comment`; `test_subscription_extends_from_end` (active till +10d, extend 30 → new `starts_at` == old `ends_at`); `test_seller_shops_lists_only_own`; `test_admin_change_user_role` and `test_admin_cannot_demote_self`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: seller applications and subscriptions`

---

### Task 13: Moderation — change requests and seller promotions

**Files:**
- Create: `app/modules/moderation/{__init__,models,schemas,service,admin_router}.py`, `app/modules/sellers/seller_router.py`
- Test: `tests/moderation/test_change_requests.py`, `tests/sellers/test_seller_promotions.py`

**Interfaces:**
- Consumes: `ShopUpdate`, `update_shop`, `PromotionCreate`, `PromotionUpdate`, `create_promotion`, `update_promotion`, `has_active_subscription`, `notify_promotion_published`, `push_notifications`.
- Produces:
  - `EntityType(StrEnum)`: `shop|promotion`.
  - `ChangeRequest`: `entity_type`, `entity_id`, `author_id` CASCADE, `payload` JSONB, `status` default `pending`, `admin_comment`, `reviewed_by`, `reviewed_at`; partial unique index on `(entity_type, entity_id, author_id) WHERE status='pending'`.
  - Seller payload schemas: `SellerShopUpdate` = `ShopUpdate` minus location/`mall_id`/`city_id`/`owner` fields (seller cannot move the shop); `PromotionUpdate`.
  - `async def submit_change_request(session, author: User, entity_type: EntityType, entity_id: int, payload: dict) -> ChangeRequest` — validates ownership (403 `"not_owner"`), active subscription (403 `"subscription_required"`), payload via schema (422), non-empty payload (422 `"empty_change"`); replaces existing pending request of same author+entity (update payload, keep one row).
  - `async def approve_change_request(session, cr, admin) -> ChangeRequest` — re-checks entity exists and subscription active; otherwise sets `rejected` with comment `"entity_deleted"` / `"subscription_expired"` and returns it (HTTP 200, status shows outcome); else applies via `update_shop` / `update_promotion` with the validated schema, sets `approved`. 409 `"already_reviewed"`.
  - `async def reject_change_request(session, cr, admin, comment: str) -> ChangeRequest`.
  - Admin routes: `GET /api/v1/admin/change-requests?status=&entity_type=` (paged; each item includes current entity snapshot `current` and `payload`); `POST /admin/change-requests/{id}/approve`; `POST /admin/change-requests/{id}/reject {comment}`.
  - Seller routes (SellerUser, ownership enforced): `POST /api/v1/seller/shops/{id}/change-requests` (body `SellerShopUpdate`) → 201 `ChangeRequestOut`; `GET /seller/change-requests`; `POST /seller/shops/{id}/promotions` (body `PromotionCreate` without `shop_id`; requires active subscription; created `pending`); `GET /seller/promotions`; `POST /seller/promotions/{id}/change-requests` (body `PromotionUpdate`).
  - Approving a promotion change request on an already-active promotion does not re-notify.
  - `GET /seller/shops` now fills `pending_change_requests`.

- [ ] **Step 1: Failing tests**
  - `test_submit_and_approve_applies` — seller changes `how_to_find_ru`; live shop unchanged before approval (`GET /shops/{id}`), changed after.
  - `test_reject_leaves_shop` — comment stored, shop unchanged.
  - `test_not_owner_403`, `test_no_subscription_403`.
  - `test_invalid_payload_422` — `{"opens_at": "25:99"}`.
  - `test_seller_cannot_change_location` — `{"mall_id": 2}` → 422 (extra forbidden).
  - `test_resubmit_replaces_pending` — two submits → one pending row with latest payload.
  - `test_approve_after_subscription_expired_autorejects` — expire subscription, approve → status `rejected`, comment `"subscription_expired"`, shop unchanged.
  - `test_approve_after_shop_deleted_autorejects`.
  - `test_seller_promotion_pending_until_admin_approves` — not in `/promotions` until admin approves; then public and notifications created.
  - `test_double_review_409`.
- [ ] **Step 2: FAIL** · **Step 3: Implement** · **Step 4: Migration, PASS**
- [ ] **Step 5: Commit** — `feat: moderation via change requests`

---

### Task 14: Migration check, README, final verification

**Files:**
- Create: `README.md`, `tests/test_migrations.py`

- [ ] **Step 1: Failing test** — `test_migrations_match_models`: on a fresh database run `alembic upgrade head`, then `alembic check` (or `compare_metadata`) reports no diff.
- [ ] **Step 2: Fix any drift** with a new autogenerated revision.
- [ ] **Step 3: README** — setup (`docker compose up -d db`, `uv sync`, `uv run alembic upgrade head`, `uv run python -m app.cli create-admin +993...`, `uv run uvicorn app.main:app --reload`), docs at `/docs`, test command, roles and moderation flow in 10 lines.
- [ ] **Step 4: Full run** — `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → all pass.
- [ ] **Step 5: Smoke** — `docker compose up --build -d`; `curl localhost:8000/health` → `{"status":"ok"}`; `/openapi.json` lists the `/api/v1` routes.
- [ ] **Step 6: Commit** — `docs: README and migration consistency test`
