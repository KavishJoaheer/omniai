"""M20 — Agent Template Marketplace routes.

Endpoints
---------
GET  /v1/marketplace/templates               — list built-in templates (filterable)
GET  /v1/marketplace/templates/{id}          — get full template with definition
POST /v1/agents/import-template              — create agent from template ID or URL
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from omniai.application.agent_service import AgentService, CreateAgentInput
from omniai.application.marketplace_service import MarketplaceService
from omniai.interfaces.http.deps import get_agent_service, get_current_principal
from omniai.interfaces.http.envelope import ok

marketplace_router = APIRouter(prefix="/v1/marketplace", tags=["marketplace"])
agents_import_router = APIRouter(prefix="/v1/agents", tags=["agents"])

_marketplace_service = MarketplaceService()


# ── Marketplace listing ───────────────────────────────────────────────────────

@marketplace_router.get("/templates")
def list_templates(
    category: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    _: object = Depends(get_current_principal),
) -> dict:
    """List available agent templates.

    Optionally filter by ``category`` (e.g. ``research``, ``support``) or
    ``tag`` (e.g. ``rag``, ``hitl``).
    """
    return ok(_marketplace_service.list_templates(category=category, tag=tag))


@marketplace_router.get("/templates/{template_id}")
def get_template(
    template_id: str,
    _: object = Depends(get_current_principal),
) -> dict:
    """Return the full template definition."""
    try:
        return ok(_marketplace_service.get_template(template_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── Import from template ──────────────────────────────────────────────────────

class ImportTemplateRequest(BaseModel):
    """Request body for importing a template as a new agent.

    Provide either ``template_id`` (a built-in template key) **or** ``url``
    (a publicly accessible JSON endpoint), but not both.
    """
    template_id: str | None = Field(default=None)
    url: str | None = Field(default=None)
    name: str | None = Field(default=None, min_length=1, max_length=128,
                              description="Override the template's default name.")
    description: str | None = Field(default=None, max_length=2000)


@agents_import_router.post("/import-template", status_code=status.HTTP_201_CREATED)
async def import_template(
    body: ImportTemplateRequest,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """Create a new agent from a marketplace template or a remote URL.

    The created agent will have its ``template_id`` set so you can track
    which template it was imported from.
    """
    if not body.template_id and not body.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'template_id' or 'url'.",
        )
    if body.template_id and body.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide 'template_id' OR 'url', not both.",
        )

    try:
        if body.template_id:
            template = _marketplace_service.get_template(body.template_id)
            tid = body.template_id
        else:
            assert body.url is not None
            template = await _marketplace_service.import_from_url(body.url)
            tid = template.get("id") or body.url[:64]
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    agent_name = body.name or template.get("name") or "Imported Agent"
    agent_desc = body.description or template.get("description")

    try:
        agent = service.create_agent(
            CreateAgentInput(
                name=agent_name,
                description=agent_desc,
                definition=template["definition"],
            ),
            template_id=tid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ok(agent, message="created")
