# Nirede backend — design

Date: 2026-11-23
Status: draft, awaiting approval

## 1. Intent

Nirede is a mobile directory for Turkmenistan: a buyer types what they want
("женское пальто") and learns **which shop sells that category and exactly where it is**
(mall, floor, shop number; or market row and place; or a standalone address in a city).

There are **no products** in the system. A shop is described by the list of categories it sells.

Revenue: sellers pay a monthly subscription (30 TMT). A subscribed shop gets a star,
ranks first in search, and its owner can edit the shop and publish promotions.
Every change from a seller is moderated by an admin.

This repo is **backend only** (REST API). The mobile client is built separately from
Figma screens in `~/Downloads/Nirede`.

## 2. Goals

- Admin CRUD for cities, malls, categories, shops, promotions.
- Category tree with arbitrary depth (`parent_id`).
- Shops either inside a mall (floor/row + number) or standalone in a city (address).
- Search by category and shop name, results grouped by mall, subscribed shops first.
- Buyer accounts by phone: favorites, "my malls", notification settings, notification feed.
- Seller flow: apply (claim an existing shop or propose a new one) → admin calls,
  takes payment offline, activates subscription → seller edits shop and adds promotions
  through moderation.
- Two languages: Turkmen (`tk`) and Russian (`ru`) for all user-facing content.

## 3. Non-goals (for now)

- Products, prices, stock.
- Online payment. Payment is offline; admin records it.
- Interactive mall map / coordinates. The Figma map is a placeholder; the API only
  returns shops per floor/row block.
- Admin web UI. Admin works through the same REST API (a UI can come later).
- Real SMS and push delivery. Both sit behind interfaces with a logging stub.

## 4. Anti-goals

- A seller edit must never make a live shop disappear from search or show unreviewed data.
- A buyer must never need an account to search and browse.
- Premium must never hide non-premium shops; it only reorders.

## 5. Approaches considered (moderation)

| Approach | Trade-off | Decision |
|---|---|---|
| **Change requests**: seller edits are stored as a `change_request` row (JSON payload, status). Live object is untouched until approval, then the payload is applied. | One moderation queue for all entity types, built-in history. Payload validated with Pydantic on submit. | **Chosen** |
| Status column on the shop itself | Shop vanishes from search or shows unreviewed data during moderation. | Rejected |
| Shadow `shop_drafts` table | Every column duplicated; categories and photos are worse. | Rejected |

New objects created by a seller (new promotion) are created with `status = pending`
and are invisible publicly until approved. Edits to existing live objects go through
`change_request`.

## 6. Stack (builder's call, stated to the user)

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 async (asyncpg), Alembic.
- PostgreSQL 16 with `pg_trgm` extension for fuzzy search.
- Auth: phone + SMS OTP, JWT access token (short) + refresh token (stored hashed in DB).
- Tooling: `uv`, `ruff`, `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, tests against
  a real Postgres (docker compose service).
- File storage: local disk behind a `Storage` interface (S3 later). Images served from `/media`.
- Docker compose: `api`, `db`.

## 7. Domain model

All user-facing text fields exist as a pair `<field>_ru` / `<field>_tk`.
All tables have `id` (bigint identity), `created_at`, `updated_at`.

### City
`name_ru`, `name_tk`, `is_active`.

### Mall
- `city_id`, `name_*`, `address_*`, `phone`, `opens_at`, `closes_at` (time, local Asia/Ashgabat),
  `description_*` (e.g. "Ряды и места вместо этажей"), `is_active`, `sort_order`.
- `layout`: enum `floors | rows`. Tolkuchka is `rows`.
- `floors_count` (for `floors`).
- `MallPhoto`: `mall_id`, `path`, `position`.
- `MallFloor`: `mall_id`, `number`, `summary_*` ("Одежда, сумки, аксессуары") — for the
  "По этажам" block. For `rows` malls this holds row blocks (e.g. label "Ряды 13–24").

### Category
`parent_id` (nullable, self FK), `name_*`, `icon` (path), `slug`, `sort_order`, `is_active`.
Root categories (`parent_id IS NULL`) are the home-screen tiles. Depth is unlimited.
Subtree queries use a recursive CTE.

### Shop
- `name`, `logo`, `phone`, `opens_at`, `closes_at`, `how_to_find_*`, `is_active`.
- Location — exactly one of two shapes (DB `CHECK` constraint):
  - **in mall**: `mall_id` set, `floor` (int, for `floors` malls) **or** `row` (str, for `rows` malls),
    `number` (str: "214", "32").
  - **standalone**: `mall_id` null, `city_id` set, `address_*` set.
  - `city_id` is always set (for in-mall shops it equals the mall's city; service enforces it)
    so city filtering is one column.
- `owner_id` (nullable FK user) — the seller who manages it.
- `ShopPhoto`: `shop_id`, `path`, `position` ("1 / 6 фото").
- `shop_categories`: M2M `shop_id`, `category_id`. A shop should link the most specific
  categories ("Пальто"); search matches subtrees, so a shop under "Пальто" is found under
  "Верхняя одежда" and "Женщинам".
- **Premium** is derived: shop has a `Subscription` with `starts_at <= now < ends_at`.
  Exposed as `is_premium` in responses. No stored flag.
- **Open now** is derived from `opens_at/closes_at` in Asia/Ashgabat; response gives
  `is_open_now` and `closes_at`.

### Subscription
`shop_id`, `starts_at`, `ends_at`, `amount` (numeric, TMT), `activated_by` (admin user),
`note`. Admin creates it after offline payment. Default period 30 days. Extending creates a
new row starting at the current `ends_at`.

### SellerApplication (the "Заявка на премиум" form)
`user_id`, `shop_id` (nullable — set when claiming an existing shop via "Это ваш магазин?"),
`shop_name`, `mall_id` (nullable), `floor`, `row`, `number`, `city_id`, `address`,
`contact_phone`, `status` (`pending | approved | rejected`), `admin_comment`, `reviewed_by`, `reviewed_at`.

Admin approval (one transaction):
1. If `shop_id` is null, create the shop from the application data.
2. Set `shop.owner_id = user`, user role becomes `seller`.
3. Optionally create the first `Subscription` in the same call (admin passes `amount`, `days`).

### ChangeRequest
`entity_type` (`shop | promotion`), `entity_id`, `author_id`, `payload` (JSONB — only the
changed fields), `status` (`pending | approved | rejected`), `admin_comment`, `reviewed_by`, `reviewed_at`.

- On submit: payload validated with the same Pydantic `ShopUpdate` / `PromotionUpdate` schema
  the admin uses; invalid → 422 immediately.
- One open (`pending`) request per entity per author; a new submit replaces the pending one.
- On approve: payload re-validated and applied in one transaction. If the entity was deleted
  meanwhile → request auto-rejected.
- Photos: seller uploads go to storage immediately but are referenced only from the payload
  (`photos: [paths]`); they become live on approval.
- Seller may submit only while the shop has an active subscription.

### Promotion
`shop_id`, `title_*`, `badge` (short label: "−30%", "2+1"), `description_*`, `image`,
`starts_at`, `ends_at`, `status` (`pending | approved | rejected`), `created_by`.
Public only when `approved` and `starts_at <= now < ends_at`.
Admin-created promotions are `approved` immediately.
"Featured" card on the promotions screen = newest active promotion of a premium shop.

### User
`phone` (unique, E.164 `+993…`), `name`, `role` (`user | seller | admin`), `language` (`ru | tk`),
`notify_favorite_shops` (bool, default true), `notify_my_malls` (bool, default true).
- `favorite_shops`: M2M user–shop (the "Сохранить" button on a shop).
- `user_malls`: M2M user–mall — "мои ТЦ". The "Сохранить" button on a mall page toggles it,
  and the profile chips edit the same list.
- `DeviceToken`: `user_id`, `token`, `platform` (`ios | android`).
- `OtpCode`: `phone`, `code_hash`, `expires_at`, `attempts`.
- `RefreshToken`: `user_id`, `token_hash`, `expires_at`, `revoked_at`.

### Notification
`user_id`, `promotion_id` (nullable), `title_*`, `body_*`, `image`, `read_at`.
Feed groups by day on the client ("Сегодня", "Вчера"); API returns `created_at`.

## 8. API surface (`/api/v1`)

Pagination: `?limit=&offset=` with `{items, total}` response. Errors: FastAPI default
`{"detail": ...}`, plus 409 for conflicts.
Language: responses carry both `*_ru` and `*_tk` fields; the client picks. (Builder's call:
simpler than header negotiation and lets the client switch language instantly.)

### Public (no auth)
- `GET /cities`
- `GET /malls?city_id=` · `GET /malls/{id}` (photos, floors summary, root categories present,
  shop count)
- `GET /malls/{id}/shops?floor=&row=&category_id=` — shops on a floor/row block, premium first
  (map bottom sheet)
- `GET /categories` (roots) · `GET /categories/{id}` (with children, 2 levels — "Категория: Женщинам"
  screen) · `GET /categories/tree`
- `GET /shops/{id}` (photos, categories, location, is_premium, is_open_now)
- `GET /search/suggest?q=&city_id=` → `{categories: [{id, name, path, shop_count}],
  malls_for_top_category: [{mall_id, name, shop_count}], shops: [...]}`
- `GET /search?category_id=|q=&city_id=&mall_id=` → shops grouped by mall
  (`[{mall, shop_count, shops:[...]}]` + group for standalone shops), within each group premium
  first then by name. Header totals: "18 магазинов в 4 торговых центрах".
  Empty result → `similar_categories` (trigram similarity on category names, plus parent of
  the best match).
- `GET /promotions?city_id=&mall_id=` → `{featured, items}`

### Auth
- `POST /auth/otp/request {phone}` — rate limited per phone (1/min, 5/hour).
- `POST /auth/otp/verify {phone, code}` → `{access_token, refresh_token, user}`;
  creates the user on first login.
- `POST /auth/refresh` · `POST /auth/logout`

### Me (user)
- `GET /me` · `PATCH /me {name, language, notify_favorite_shops, notify_my_malls}`
- `GET /me/favorites` · `PUT /me/favorites/{shop_id}` · `DELETE /me/favorites/{shop_id}`
- `GET /me/malls` · `PUT /me/malls/{mall_id}` · `DELETE /me/malls/{mall_id}`
- `GET /me/notifications` · `GET /me/notifications/unread-count` ·
  `POST /me/notifications/{id}/read` · `POST /me/notifications/read-all`
- `POST /me/devices {token, platform}` · `DELETE /me/devices/{token}`
- `POST /me/seller-applications` · `GET /me/seller-applications`

### Seller (role `seller`, owns the shop)
- `GET /seller/shops` — own shops with subscription status and pending requests
- `POST /seller/shops/{id}/change-requests` (payload = partial `ShopUpdate`)
- `GET /seller/change-requests`
- `POST /seller/shops/{id}/promotions` (created `pending`) ·
  `POST /seller/promotions/{id}/change-requests` · `GET /seller/promotions`
- `POST /seller/uploads` (image) → `{path}`

### Admin (role `admin`)
- CRUD: `/admin/cities`, `/admin/malls` (+ `/photos`, `/floors`), `/admin/categories`,
  `/admin/shops` (+ `/photos`, categories set), `/admin/promotions`
- `GET /admin/change-requests?status=` · `POST /admin/change-requests/{id}/approve` ·
  `POST /admin/change-requests/{id}/reject {comment}`
- `GET /admin/promotions?status=pending` · approve / reject
- `GET /admin/seller-applications?status=` · approve (with optional subscription) / reject
- `POST /admin/shops/{id}/subscriptions {amount, days}` · `GET /admin/shops/{id}/subscriptions`
- `GET /admin/users?role=` · `PATCH /admin/users/{id} {role}`
- `POST /admin/uploads`

First admin: created by CLI command `python -m app.cli create-admin +993...`.

## 9. Search

- Query normalization: lowercase, trim, collapse spaces; match against both `name_ru` and `name_tk`.
- Category match: `ILIKE` prefix/substring + `pg_trgm` similarity, GIN trigram index on
  category names and shop name.
- Category path for suggestions ("Женщинам › Верхняя одежда") from recursive CTE.
- `shop_count` = distinct active shops linked to the category or any descendant, in the city.
- Phrase "женское пальто" vs category "Пальто" under "Женщинам": suggestion ranks categories
  whose full path text matches all query words. (Category names in the Figma like
  "Женские пальто" are display names built from path; builder may add optional
  `search_aliases_*` text on Category to make phrases match — recommended.)
- Ordering of shops: premium first, then name.

## 10. Notifications

Trigger: a promotion becomes public (admin approves, or admin creates it).
Recipients: users with `notify_favorite_shops` who favorited the shop, ∪ users with
`notify_my_malls` whose `user_malls` contains the shop's mall. Deduplicated.
For each: insert `Notification` row, then call `PushSender.send(tokens, ...)`.
Fan-out runs in a FastAPI `BackgroundTask` (enough for current scale; a queue later).
`PushSender` has a logging stub now, FCM implementation later.

## 11. Code layout

Feature modules:

```
app/
  main.py, config.py, db.py, deps.py, security.py, storage.py, cli.py
  modules/
    cities/      models.py schemas.py service.py router.py admin_router.py
    malls/
    categories/
    shops/
    promotions/
    search/
    users/       (auth, me, favorites, devices)
    notifications/
    sellers/     (applications, subscriptions, seller routes)
    moderation/  (change requests)
alembic/
tests/
```

Routers stay thin; business rules live in `service.py`; queries in the service via
SQLAlchemy (no separate repository layer unless it earns its place).

## 12. Testing

- pytest against real Postgres (compose), each test in a rolled-back transaction.
- Required coverage: moderation apply/reject paths, seller cannot edit without active
  subscription or for a shop they do not own, search grouping and premium ordering, category
  subtree matching, shop location CHECK constraint, OTP rate limit and attempts,
  notification recipient selection.

## 13. Left to the builder

- Exact JWT lifetimes (suggest access 30 min, refresh 30 days).
- OTP length and TTL (suggest 4 digits, 5 min, 5 attempts).
- Image limits (suggest jpeg/png/webp, 5 MB, resize to max 1600 px).
- Index details beyond those named above.
