from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.modules.cities import admin_router as cities_admin
from app.modules.cities import router as cities
from app.modules.uploads import router as uploads
from app.modules.users.router import auth_router, me_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="Nirede API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    routers = [
        auth_router,
        me_router,
        cities.router,
        cities_admin.router,
        uploads.admin_router,
        uploads.seller_router,
    ]
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)

    settings = get_settings()
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount(settings.media_url, StaticFiles(directory=settings.media_dir), name="media")
    return app


app = create_app()
