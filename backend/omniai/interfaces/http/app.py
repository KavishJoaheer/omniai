import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from omniai.bootstrap.container import build_container
from omniai.config.settings import get_settings
from omniai.interfaces.http.routes.admin import router as admin_router
from omniai.interfaces.http.routes.agents import router as agents_router
from omniai.interfaces.http.routes.api_keys import router as api_keys_router
from omniai.interfaces.http.routes.auth import router as auth_router
from omniai.interfaces.http.routes.chat import router as chat_router
from omniai.interfaces.http.routes.collections import router as collections_router
from omniai.interfaces.http.routes.connectors import router as connectors_router
from omniai.interfaces.http.routes.sandbox import router as sandbox_router
from omniai.interfaces.http.routes.deployments import (
    admin_router as deployments_admin_router,
    public_router as deployments_public_router,
)
from omniai.interfaces.http.routes.documents import (
    collection_router as documents_collection_router,
    document_router as documents_router,
)
from omniai.interfaces.http.routes.providers import router as providers_router
from omniai.interfaces.http.routes.retrieval import router as retrieval_router
from omniai.interfaces.http.routes.system import router as system_router
from omniai.interfaces.http.routes.teams import router as teams_router
from omniai.interfaces.http.routes.tenants import router as tenants_router
from omniai.observability.rate_limit import TokenBucketLimiter


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

    rate_limiter = TokenBucketLimiter(
        capacity=settings.rate_limit_per_minute,
        refill_per_second=settings.rate_limit_per_minute / 60.0,
    )
    app.state.rate_limiter = rate_limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _exempt_paths = ("/v1/health", "/v1/metrics", "/docs", "/openapi.json", "/c/")

    @app.middleware("http")
    async def observe_and_limit(request: Request, call_next):
        path = request.url.path
        method = request.method

        # Rate limit by API key, session token, or remote IP. /metrics and
        # /health are always exempt so monitoring never gets locked out.
        if not any(path.startswith(p) for p in _exempt_paths):
            key = (
                request.headers.get("x-api-key")
                or request.cookies.get(settings.session_cookie_name)
                or (request.client.host if request.client else "anonymous")
            )
            allowed, retry_after = rate_limiter.acquire(key)
            if not allowed:
                container.metrics.rate_limited_counter.labels(tenant=key[:32]).inc()
                return JSONResponse(
                    status_code=429,
                    content={"error": "rate_limited", "retry_after_seconds": round(retry_after, 2)},
                    headers={"Retry-After": str(int(retry_after) + 1)},
                )

        started = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            container.metrics.observe_request(
                method=method, path=path, status=500, duration=time.perf_counter() - started
            )
            raise
        container.metrics.observe_request(
            method=method, path=path, status=status_code, duration=time.perf_counter() - started
        )
        return response

    @app.get("/v1/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        body, content_type = container.metrics.render_prometheus()
        return Response(content=body, media_type=content_type)

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(api_keys_router)
    app.include_router(tenants_router)
    app.include_router(teams_router)
    app.include_router(admin_router)
    app.include_router(collections_router)
    app.include_router(documents_collection_router)
    app.include_router(documents_router)
    app.include_router(providers_router)
    app.include_router(retrieval_router)
    app.include_router(chat_router)
    app.include_router(agents_router)
    app.include_router(connectors_router)
    app.include_router(deployments_admin_router)
    app.include_router(deployments_public_router)
    app.include_router(sandbox_router)

    @app.on_event("startup")
    async def _start_connector_scheduler() -> None:
        container.connector_scheduler.start()

    @app.on_event("shutdown")
    async def _stop_connector_scheduler() -> None:
        await container.connector_scheduler.stop()

    @app.on_event("shutdown")
    async def _persist_search_index() -> None:
        from omniai.adapters.search.in_memory import InMemorySearchEngine as _InMem
        if isinstance(container.search_engine, _InMem):
            container.search_engine.save_snapshot()

    return app
