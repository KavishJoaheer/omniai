from fastapi import APIRouter, Request

from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {
            "name": settings.app_name,
            "environment": settings.app_env,
            "status": "healthy",
        }
    )


# /v1/metrics is registered directly in app.py to return real Prometheus output
