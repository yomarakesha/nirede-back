import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.modules.categories import admin_router as categories_admin
from app.modules.categories import router as categories
from app.modules.cities import admin_router as cities_admin
from app.modules.cities import router as cities
from app.modules.malls import admin_router as malls_admin
from app.modules.malls import router as malls
from app.modules.moderation import admin_router as moderation_admin
from app.modules.notifications import router as notifications
from app.modules.promotions import admin_router as promotions_admin
from app.modules.promotions import router as promotions
from app.modules.search import router as search
from app.modules.sellers import admin_router as sellers_admin
from app.modules.sellers import router as sellers
from app.modules.sellers import seller_router
from app.modules.shops import admin_router as shops_admin
from app.modules.shops import router as shops
from app.modules.uploads import router as uploads
from app.modules.users import admin_router as users_admin
from app.modules.users.router import auth_router, me_router

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # docs_url=None: the default /docs page pulls Swagger UI from a CDN that is not
    # always reachable, so we serve vendored copies from app/static/swagger instead.
    app = FastAPI(title="Nirede API", version="0.1.0", docs_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        # Relative URLs so the page also works behind a proxy that mounts the API
        # under a path prefix (e.g. nginx at /nirede/) without setting root_path.
        return get_swagger_ui_html(
            openapi_url=app.openapi_url.lstrip("/"),
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url.lstrip("/"),
            swagger_js_url="static/swagger/swagger-ui-bundle.js",
            swagger_css_url="static/swagger/swagger-ui.css",
            swagger_favicon_url="static/swagger/favicon-32x32.png",
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    async def swagger_ui_redirect() -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    routers = [
        auth_router,
        me_router,
        cities.router,
        cities_admin.router,
        malls.router,
        malls_admin.router,
        categories.router,
        categories_admin.router,
        shops.router,
        shops_admin.router,
        search.router,
        promotions.router,
        promotions_admin.router,
        notifications.router,
        sellers.me_router,
        sellers.seller_router,
        sellers_admin.router,
        users_admin.router,
        seller_router.router,
        moderation_admin.router,
        uploads.admin_router,
        uploads.seller_router,
    ]
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)

    settings = get_settings()
    if settings.cors_origins:
        # Bearer tokens, no cookies, so credentials stay off and "*" is allowed.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    app.mount(settings.media_url, StaticFiles(directory=settings.media_dir), name="media")
    return app


app = create_app()
