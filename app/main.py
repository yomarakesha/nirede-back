from fastapi import FastAPI

from app.modules.cities import admin_router as cities_admin
from app.modules.cities import router as cities
from app.modules.users.router import auth_router, me_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="Nirede API", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    routers = [auth_router, me_router, cities.router, cities_admin.router]
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
