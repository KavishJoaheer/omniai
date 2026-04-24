from fastapi import APIRouter, Depends, HTTPException, status

from omniai.application.services import CreateCollectionInput, KnowledgeService
from omniai.interfaces.http.deps import get_current_principal, get_knowledge_service, get_metrics
from omniai.interfaces.http.envelope import ok
from omniai.observability.metrics import MetricsRegistry

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
