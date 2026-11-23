# Nirede — backend

REST API справочника «где в Ашхабаде продаётся нужная категория товаров»: торговые центры,
магазины (в ТЦ или отдельно в городе), дерево категорий, поиск, акции, избранное,
уведомления, подписка продавцов и модерация их правок.

Стек: Python 3.13, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, PostgreSQL 16 + `pg_trgm`.

Дизайн: `docs/superpowers/specs/2026-11-23-nirede-backend-design.md`.

## Запуск локально

```bash
cp .env.example .env              # поменяйте JWT_SECRET
docker compose up -d db           # Postgres на localhost:5433, плюс база nirede_test
uv sync
uv run alembic upgrade head
uv run python -m app.cli create-admin +99365123456
uv run uvicorn app.main:app --reload
```

- Swagger: http://localhost:8000/docs, OpenAPI: `/openapi.json`.
- Фото отдаются из `/media` (папка `media/`).
- SMS и push пока заглушки: при `SMS_DEBUG_LOG=true` код входа виден в логе сервера.

Всё в Docker: `docker compose up --build` (API на :8000, миграции применяются при старте).

## Postman

`postman/collections/nirede.postman_collection.json` и окружение `postman/environments/local.postman_environment.json` —
импортируйте в Postman. Инструкция по входу в описании коллекции. После изменения API пересоберите:
`uv run python scripts/gen_postman.py`.

## Тесты и линтер

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Тесты идут против настоящего Postgres (`TEST_DATABASE_URL`); каждый тест в откатываемой
транзакции. `tests/test_migrations.py` проверяет, что миграции совпадают с моделями.

## Как устроено

- `app/modules/<домен>/` — `models.py`, `schemas.py`, `service.py`, `router.py`, `admin_router.py`.
- Все тексты для пользователя хранятся парой полей `*_ru` / `*_tk`; API отдаёт обе, язык выбирает клиент.
- Списки: `?limit=&offset=` → `{"items": [...], "total": N}`. Ошибки: `{"detail": "код_ошибки"}`.
- Префикс API: `/api/v1`. Зоны: публичная, `/me` (пользователь), `/seller`, `/admin`.

### Роли и поток продавца

1. Вход по телефону: `POST /auth/otp/request` → SMS-код → `POST /auth/otp/verify` → JWT access + refresh.
2. Пользователь подаёт заявку `POST /me/seller-applications` (свой существующий магазин или новый).
3. Админ звонит, принимает оплату вне приложения и одобряет заявку:
   `POST /admin/seller-applications/{id}/approve` с подпиской (30 TMT, 30 дней). Пользователь становится `seller`.
4. Пока подписка активна, у магазина звезда, он первый в поиске, а продавец может:
   - предлагать правки магазина `POST /seller/shops/{id}/change-requests`;
   - создавать акции `POST /seller/shops/{id}/promotions` (статус `pending`).
5. Админ модерирует: `/admin/change-requests`, `/admin/promotions?status=pending`.
   Живой магазин не меняется, пока правку не одобрили. Если к моменту одобрения подписка
   кончилась или объект удалён, правка отклоняется автоматически с причиной в `admin_comment`.
6. Одобренная активная акция рассылается тем, у кого магазин в избранном или его ТЦ в «моих ТЦ».

### Поиск

- `GET /search/suggest?q=` — категории (с путём и числом магазинов), ТЦ для лучшей категории, магазины по названию.
- `GET /search?category_id=` или `?q=` — магазины, сгруппированные по ТЦ, премиум первыми;
  при пустом результате `similar_categories`.
- Категория находит магазины всего своего поддерева. Чтобы фраза вроде «женское пальто» находила
  «Женщинам › Верхняя одежда › Пальто», заполните у категории `search_aliases_ru` / `search_aliases_tk`.
- Регистронезависимый поиск по туркменским буквам зависит от локали БД: нужна UTF-8 локаль
  (`en_US.utf8`, как в `docker-compose.yml`), не `C`.

## Продакшен

- `ENV=prod` требует `JWT_SECRET` длиной от 32 байт (иначе приложение не стартует).
- `SMS_DEBUG_LOG` в проде не включать.
- Перед запуском подключите реальные `SmsSender` (`app/modules/users/sms.py`) и
  `PushSender` (`app/modules/notifications/push.py`).
