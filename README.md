# Nirede

Монорепозиторий проекта Nirede.

| Папка | Что внутри |
|-------|------------|
| `backend/` | API на FastAPI (PostgreSQL, Alembic). Запуск и разработка — в `backend/README.md`. |
| `frontend/admin/` | Веб-админка. |
| `mobile/` | Мобильное приложение. |

Команды бэкенда запускайте из папки `backend/`:

```bash
cd backend
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```
