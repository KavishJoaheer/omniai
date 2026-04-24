from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from omniai.interfaces.http.deps import get_metrics
from omniai.interfaces.http.envelope import ok
from omniai.observability.metrics import MetricsRegistry

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


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics(metrics_registry: MetricsRegistry = Depends(get_metrics)) -> str:
    return metrics_registry.render_prometheus()
