from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from omniai.application.ingestion_service import IngestionService
from omniai.application.services import CreateCollectionInput, KnowledgeService, UpdateCollectionInput
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_db_session,
    get_ingestion_service,
    get_knowledge_service,
    get_metrics,
    get_search_engine,
)
from omniai.interfaces.http.envelope import ok
from omniai.observability.audit import record_audit_event
from omniai.observability.metrics import MetricsRegistry
from omniai.ports.search_engine import SearchEnginePort

router = APIRouter(prefix="/v1/collections", tags=["collections"])


@router.get("")
def list_collections(
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    _=Depends(get_current_principal),
) -> dict:
    collections = service.list_collections()
    metrics.collections_total = service.count_collections()
    return ok([collection.model_dump(mode="json") for collection in collections])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CreateCollectionInput,
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    _=Depends(get_current_principal),
) -> dict:
    try:
        collection = service.create_collection(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    metrics.collections_total = service.count_collections()
    return ok(collection.model_dump(mode="json"), message="created")


@router.get("/{collection_id}")
def get_collection(
    collection_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    _=Depends(get_current_principal),
) -> dict:
    try:
        collection = service.get_collection(collection_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(collection.model_dump(mode="json"))


@router.patch("/{collection_id}")
def update_collection(
    collection_id: str,
    payload: UpdateCollectionInput,
    service: KnowledgeService = Depends(get_knowledge_service),
    _=Depends(get_current_principal),
) -> dict:
    try:
        collection = service.update_collection(collection_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ok(collection.model_dump(mode="json"))


@router.delete("/{collection_id}")
def delete_collection(
    collection_id: str,
    ingestion: IngestionService = Depends(get_ingestion_service),
    search_engine: SearchEnginePort = Depends(get_search_engine),
    metrics: MetricsRegistry = Depends(get_metrics),
    session: Session = Depends(get_db_session),
    principal=Depends(get_current_principal),
) -> dict:
    try:
        ingestion.delete_collection(collection_id=collection_id, search_engine=search_engine)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    metrics.collections_total = max(0, metrics.collections_total - 1)
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="collection.delete",
        target_type="collection",
        target_id=collection_id,
    )
    return ok({"deleted": collection_id})


@router.get("/{collection_id}/graph")
def list_collection_graph(
    collection_id: str,
    entity: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: KnowledgeService = Depends(get_knowledge_service),
    _=Depends(get_current_principal),
) -> dict:
    try:
        service.get_collection(collection_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    triples = service.list_graph_triples(
        collection_id=collection_id,
        entity=entity,
        limit=limit,
        offset=offset,
    )
    return ok([triple.model_dump(mode="json") for triple in triples])


# ---- per-collection memberships --------------------------------------------


class UpsertMembershipRequest(BaseModel):
    user_id: str = Field(min_length=1)
    role: str = Field(pattern="^(OWNER|EDITOR|VIEWER)$")


@router.get("/{collection_id}/members")
def list_collection_members(
    collection_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    _=Depends(get_current_principal),
) -> dict:
    try:
        members = service.list_collection_members(collection_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok([m.model_dump(mode="json") for m in members])


@router.post("/{collection_id}/members", status_code=status.HTTP_201_CREATED)
def upsert_collection_member(
    collection_id: str,
    payload: UpsertMembershipRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    session: Session = Depends(get_db_session),
    principal=Depends(get_current_principal),
) -> dict:
    try:
        membership = service.upsert_collection_member(
            collection_id=collection_id,
            user_id=payload.user_id,
            role=payload.role,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="collection.member.upsert",
        target_type="collection",
        target_id=collection_id,
        detail={"user_id": payload.user_id, "role": payload.role},
    )
    return ok(membership.model_dump(mode="json"), message="upserted")


@router.delete("/{collection_id}/members/{user_id}")
def remove_collection_member(
    collection_id: str,
    user_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    session: Session = Depends(get_db_session),
    principal=Depends(get_current_principal),
) -> dict:
    try:
        service.remove_collection_member(collection_id=collection_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_audit_event(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="collection.member.remove",
        target_type="collection",
        target_id=collection_id,
        detail={"user_id": user_id},
    )
    return ok({"removed": user_id})
