from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from omniai.bootstrap.container import build_container
from omniai.config.settings import get_settings
from omniai.interfaces.http.routes.admin import router as admin_router
from omniai.interfaces.http.routes.api_keys import router as api_keys_router
from omniai.interfaces.http.routes.auth import router as auth_router
from omniai.interfaces.http.routes.collections import router as collections_router
from omniai.interfaces.http.routes.documents import router as documents_router
from omniai.interfaces.http.routes.providers import router as providers_router
from omniai.interfaces.http.routes.system import router as system_router
from omniai.interfaces.http.routes.teams import router as teams_router
from omniai.interfaces.http.routes.tenants import router as tenants_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    container = build_container(settings)
    app.state.container = container
    app.state.settings = settings  # legacy alias
    app.state.database = container.database  # legacy alias
    app.state.metrics = container.metrics  # legacy alias
    app.state.default_tenant_id = container.default_tenant_id  # legacy alias

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        container.metrics.http_requests_total += 1
        response = await call_next(request)
        return response

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(tenants_router)
    app.include_router(teams_router)
    app.include_router(admin_router)
    app.include_router(collections_router)
    app.include_router(documents_router)
    app.include_router(providers_router)

    return app
