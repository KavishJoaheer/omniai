"""M16 — Observability & Cost routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from omniai.application.auth_service import AuthService, AuthenticatedPrincipal
from omniai.application.observability_service import ObservabilityService, RetrievalFeedbackInput
from omniai.interfaces.http.deps import get_auth_service, get_current_principal, require_admin_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/observability", tags=["observability"])


def _get_obs_service(auth_service: AuthService = Depends(get_auth_service)) -> ObservabilityService:
    return ObservabilityService(auth_service._session, auth_service._settings)


@router.get("/cost")
def cost_dashboard(
    principal: AuthenticatedPrincipal = Depends(require_admin_principal),
    days: int = Query(default=30, ge=1, le=365),
    svc: ObservabilityService = Depends(_get_obs_service),
) -> dict:
    """Per-tenant LLM token usage + estimated cost for the last N days."""
    return ok(svc.get_cost_dashboard(principal, days=days))


@router.post("/retrieval-feedback")
def record_retrieval_feedback(
    payload: RetrievalFeedbackInput,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    svc: ObservabilityService = Depends(_get_obs_service),
) -> dict:
    """Record thumbs-up / thumbs-down for a retrieved chunk."""
    return ok(svc.record_feedback(principal, payload))


@router.get("/quality")
def quality_metrics(
    principal: AuthenticatedPrincipal = Depends(require_admin_principal),
    days: int = Query(default=30, ge=1, le=365),
    svc: ObservabilityService = Depends(_get_obs_service),
) -> dict:
    """NDCG@10 and hit-rate computed from collected retrieval feedback."""
    return ok(svc.get_quality_metrics(principal, days=days))
