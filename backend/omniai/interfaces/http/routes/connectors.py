from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import (
    SqlAlchemyConnectorStore,
)
from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.application.connector_service import ConnectorService
from omniai.application.ingestion_service import IngestionService
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_db_session,
    get_ingestion_service,
)
from omniai.interfaces.http.envelope import ok
from omniai.observability.audit import record_audit_event
from omniai.security.permissions import Perm, assert_permission

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


class ConnectorOut(BaseModel):
    id: str
    collection_id: str
    name: str
    kind: str
    config: dict
    enabled: bool
    sync_interval_seconds: int
    last_sync_at: datetime | None
    last_error: str | None
    last_synced_count: int
    created_at: datetime
    updated_at: datetime


class CreateConnectorRequest(BaseModel):
    collection_id: str
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(local_folder|s3|web_crawler)$")
    config: dict
    sync_interval_seconds: int = Field(default=300, ge=30, le=86400)


class UpdateConnectorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    config: dict | None = None
    enabled: bool | None = None
    sync_interval_seconds: int | None = Field(default=None, ge=30, le=86400)


def _service(session: Session, principal: AuthenticatedPrincipal, ingestion: IngestionService) -> ConnectorService:
    return ConnectorService(
        store=SqlAlchemyConnectorStore(session, principal.tenant_id),
        ingestion=ingestion,
        tenant_id=principal.tenant_id,
    )


def _to_out(c) -> ConnectorOut:
    return ConnectorOut(
        id=c.id,
        collection_id=c.collection_id,
        name=c.name,
        kind=c.kind,
        config=c.config,
        enabled=c.enabled,
        sync_interval_seconds=c.sync_interval_seconds,
        last_sync_at=c.last_sync_at,
        last_error=c.last_error,
        last_synced_count=c.last_synced_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("")
def list_connectors(
    collection_id: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    service = _service(session, principal, ingestion)
    items = service.list(collection_id=collection_id)
    return ok([_to_out(c).model_dump(mode="json") for c in items])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_connector(
    body: CreateConnectorRequest,
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    service = _service(session, principal, ingestion)
    try:
        connector = service.create(
            collection_id=body.collection_id,
            name=body.name,
            kind=body.kind,
            config=body.config,
            sync_interval_seconds=body.sync_interval_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="connector.create",
        target_type="connector",
        target_id=connector.id,
        detail={"kind": connector.kind, "collection_id": connector.collection_id},
    )
    return ok(_to_out(connector).model_dump(mode="json"), message="created")


@router.get("/{connector_id}")
def get_connector(
    connector_id: str,
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    service = _service(session, principal, ingestion)
    try:
        connector = service.get(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(_to_out(connector).model_dump(mode="json"))


@router.patch("/{connector_id}")
def update_connector(
    connector_id: str,
    body: UpdateConnectorRequest,
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    service = _service(session, principal, ingestion)
    try:
        connector = service.update(
            connector_id,
            name=body.name,
            config=body.config,
            enabled=body.enabled,
            sync_interval_seconds=body.sync_interval_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(_to_out(connector).model_dump(mode="json"))


@router.delete("/{connector_id}")
def delete_connector(
    connector_id: str,
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    service = _service(session, principal, ingestion)
    try:
        service.delete(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="connector.delete",
        target_type="connector",
        target_id=connector_id,
    )
    return ok({"deleted": connector_id})


@router.post("/{connector_id}/sync")
async def trigger_sync(
    connector_id: str,
    session: Session = Depends(get_db_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    service = _service(session, principal, ingestion)
    try:
        report = await service.sync(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(report.model_dump(mode="json"))
