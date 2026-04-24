from fastapi import APIRouter, Depends, HTTPException, status

from omniai.application.services import CreateDocumentInput, KnowledgeService
from omniai.interfaces.http.deps import get_current_principal, get_knowledge_service, get_metrics
from omniai.interfaces.http.envelope import ok
from omniai.observability.metrics import MetricsRegistry

router = APIRouter(prefix="/v1/collections/{collection_id}/documents", tags=["documents"])


@router.get("")
def list_documents(
    collection_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    _=Depends(get_current_principal),
) -> dict:
    try:
        documents = service.list_documents(collection_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    metrics.documents_total = service.count_documents()
    return ok([document.model_dump(mode="json") for document in documents])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_document(
    collection_id: str,
    payload: CreateDocumentInput,
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    _=Depends(get_current_principal),
) -> dict:
    try:
        document = service.create_document(collection_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    metrics.documents_total = service.count_documents()
    return ok(document.model_dump(mode="json"), message="created")
