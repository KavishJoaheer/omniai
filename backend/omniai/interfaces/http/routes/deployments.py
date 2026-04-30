"""Deploy Manager — admin CRUD + public chat surface.

Two routers:
  - `admin_router` mounted at /v1/deployments, requires authentication.
  - `public_router` mounted at /c, no authentication required when the
    deployment has anonymous_allowed=true.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import (
    DeploymentBySlugLookup,
    SqlAlchemyDeploymentStore,
    SqlAlchemyKnowledgeStore,
)
from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.application.chat_service import ChatService, _citation_to_dict
from omniai.application.deployment_service import (
    DeploymentQuotaExceeded,
    DeploymentService,
    validate_slug,
)
from omniai.application.retrieval_service import RetrievalService
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_db_session,
    get_search_engine,
    get_secret_box,
)
from omniai.interfaces.http.envelope import ok
from omniai.observability.audit import record_audit_event
from omniai.plugins.embedding_providers.factory import build_embedding_provider
from omniai.security.permissions import Perm, assert_permission

admin_router = APIRouter(prefix="/v1/deployments", tags=["deployments"])
public_router = APIRouter(prefix="/c", tags=["public-deployments"])


# ---- Schemas ---------------------------------------------------------------


class DeploymentOut(BaseModel):
    id: str
    name: str
    slug: str
    kind: str
    target_kind: str
    target_id: str
    system_prompt_override: str | None
    model_provider: str | None
    model_name: str | None
    anonymous_allowed: bool
    rate_limit_per_minute: int
    daily_message_quota: int
    branding: dict
    status: str
    version: int
    message_count: int
    today_message_count: int
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime
    public_url_path: str  # convenience: "/c/<slug>"


def _to_out(d) -> DeploymentOut:
    return DeploymentOut(
        id=d.id,
        name=d.name,
        slug=d.slug,
        kind=d.kind,
        target_kind=d.target_kind,
        target_id=d.target_id,
        system_prompt_override=d.system_prompt_override,
        model_provider=d.model_provider,
        model_name=d.model_name,
        anonymous_allowed=d.anonymous_allowed,
        rate_limit_per_minute=d.rate_limit_per_minute,
        daily_message_quota=d.daily_message_quota,
        branding=d.branding,
        status=d.status,
        version=d.version,
        message_count=d.message_count,
        today_message_count=d.today_message_count,
        last_message_at=d.last_message_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
        public_url_path=f"/c/{d.slug}",
    )


class CreateDeploymentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    kind: str = Field(default="public_chat", pattern="^(public_chat|webhook)$")
    target_kind: str = Field(pattern="^(collection|agent)$")
    target_id: str
    system_prompt_override: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    anonymous_allowed: bool = True
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    daily_message_quota: int = Field(default=500, ge=0, le=1_000_000)
    branding: dict = Field(default_factory=dict)


class UpdateDeploymentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    system_prompt_override: str | None = None
    anonymous_allowed: bool | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=10_000)
    daily_message_quota: int | None = Field(default=None, ge=0, le=1_000_000)
    branding: dict | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|PAUSED)$")


class PublicChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


# ---- Admin routes ----------------------------------------------------------


def _service(session: Session, principal: AuthenticatedPrincipal) -> DeploymentService:
    return DeploymentService(
        store=SqlAlchemyDeploymentStore(session, principal.tenant_id),
        tenant_id=principal.tenant_id,
    )


@admin_router.get("")
def list_deployments(
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    items = _service(session, principal).list()
    return ok([_to_out(d).model_dump(mode="json") for d in items])


@admin_router.post("", status_code=status.HTTP_201_CREATED)
def create_deployment(
    body: CreateDeploymentRequest,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    if body.slug:
        try:
            validate_slug(body.slug)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Verify the target exists in this tenant before publishing
    knowledge_store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    if body.target_kind == "collection":
        try:
            knowledge_store.get_collection(body.target_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        deployment = _service(session, principal).create(
            name=body.name,
            slug=body.slug,
            kind=body.kind,
            target_kind=body.target_kind,
            target_id=body.target_id,
            system_prompt_override=body.system_prompt_override,
            model_provider=body.model_provider,
            model_name=body.model_name,
            anonymous_allowed=body.anonymous_allowed,
            rate_limit_per_minute=body.rate_limit_per_minute,
            daily_message_quota=body.daily_message_quota,
            branding=body.branding,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="deployment.create",
        target_type="deployment",
        target_id=deployment.id,
        detail={"slug": deployment.slug, "kind": deployment.kind, "target_kind": deployment.target_kind},
    )
    return ok(_to_out(deployment).model_dump(mode="json"), message="published")


@admin_router.get("/{deployment_id}")
def get_deployment(
    deployment_id: str,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        deployment = _service(session, principal).get(deployment_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(_to_out(deployment).model_dump(mode="json"))


@admin_router.patch("/{deployment_id}")
def update_deployment(
    deployment_id: str,
    body: UpdateDeploymentRequest,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        deployment = _service(session, principal).update(
            deployment_id,
            name=body.name,
            system_prompt_override=body.system_prompt_override,
            anonymous_allowed=body.anonymous_allowed,
            rate_limit_per_minute=body.rate_limit_per_minute,
            daily_message_quota=body.daily_message_quota,
            branding=body.branding,
            status=body.status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(_to_out(deployment).model_dump(mode="json"))


@admin_router.delete("/{deployment_id}")
def delete_deployment(
    deployment_id: str,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        _service(session, principal).delete(deployment_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="deployment.delete",
        target_type="deployment",
        target_id=deployment_id,
    )
    return ok({"deleted": deployment_id})


# ---- Public surface --------------------------------------------------------


def _resolve_public(session: Session, slug: str):
    lookup = DeploymentBySlugLookup(session)
    found = lookup.find(slug)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")
    tenant_id, deployment = found
    return tenant_id, deployment, lookup


@public_router.get("/{slug}/info")
def public_deployment_info(slug: str, session: Session = Depends(get_db_session)) -> dict:
    tenant_id, deployment, _ = _resolve_public(session, slug)
    # Return only what's safe for an anonymous caller
    return ok(
        {
            "name": deployment.name,
            "slug": deployment.slug,
            "branding": deployment.branding,
            "anonymous_allowed": deployment.anonymous_allowed,
            "kind": deployment.kind,
            "target_kind": deployment.target_kind,
        }
    )


@public_router.post("/{slug}/chat")
async def public_chat(
    slug: str,
    body: PublicChatRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    secret_box=Depends(get_secret_box),
    search_engine=Depends(get_search_engine),
) -> StreamingResponse:
    if not body.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is required.")

    tenant_id, deployment, lookup = _resolve_public(session, slug)

    # Quota + status checks
    try:
        DeploymentService.assert_active(deployment)
        DeploymentService.assert_within_daily_quota(deployment)
    except DeploymentQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    if not deployment.anonymous_allowed:
        # Future: check for a deployment-scoped API key in headers. For now we
        # simply refuse anonymous access when the owner disabled it.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This deployment requires authentication.",
        )

    # Build a chat service rooted in the deployment's tenant — using the
    # collection/agent the owner published. The deployment is not associated
    # with any user, so we pass user_id=None.
    settings = request.app.state.container.settings
    knowledge_store = SqlAlchemyKnowledgeStore(session, tenant_id)
    embedding_provider, _ = build_embedding_provider(
        session=session,
        settings=settings,
        tenant_id=tenant_id,
        requested_model="nomic-embed-text",
    )
    retrieval_service = RetrievalService(
        search_engine=search_engine,
        embedding_provider=embedding_provider,
        tenant_id=tenant_id,
        store=knowledge_store,
        reranker=request.app.state.container.reranker,
    )
    chat_service = ChatService(
        session=session,
        settings=settings,
        secret_box=secret_box,
        retrieval_service=retrieval_service,
        tenant_id=tenant_id,
        user_id=None,
    )

    # Scope retrieval to the deployment's collection (or, for an agent target,
    # rely on the agent definition_snapshot — Phase 2).
    collection_ids: list[str] | None = None
    if deployment.target_kind == "collection":
        collection_ids = [deployment.target_id]

    # Increment counters BEFORE streaming so concurrent requests can see the
    # new today_count (small race vs. the quota check is acceptable).
    lookup.increment_counters(deployment.id)

    async def event_stream():
        try:
            async for event in chat_service.stream_message(
                conversation_id=body.conversation_id,
                user_text=body.message,
                collection_ids=collection_ids,
                system_prompt=deployment.system_prompt_override,
                model_provider=deployment.model_provider,
                model_name=deployment.model_name,
            ):
                payload: dict = {"kind": event.kind}
                if event.kind == "citations":
                    payload["citations"] = [_citation_to_dict(c) for c in event.citations]
                    if event.conversation_id:
                        payload["conversation_id"] = event.conversation_id
                elif event.kind == "graph":
                    payload["graph_lines"] = event.graph_lines
                elif event.kind == "delta":
                    payload["delta"] = event.delta or ""
                elif event.kind == "done":
                    payload["finish_reason"] = event.finish_reason
                    payload["conversation_id"] = event.conversation_id
                    payload["message_id"] = event.message_id
                elif event.kind == "error":
                    payload["error"] = event.error
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as exc:  # pragma: no cover
            yield f"data: {json.dumps({'kind': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
