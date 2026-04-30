from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from omniai.application.ingestion_service import IngestionService
from omniai.application.services import CreateDocumentInput, KnowledgeService, UpdateCollectionInput
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_ingestion_service,
    get_job_queue,
    get_knowledge_service,
    get_metrics,
    get_object_store,
    get_search_engine,
)
from omniai.interfaces.http.envelope import ok
from omniai.observability.metrics import MetricsRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.security.permissions import Perm, assert_permission
from omniai.workers.indexing import INDEX_JOB_NAME

collection_router = APIRouter(prefix="/v1/collections/{collection_id}/documents", tags=["documents"])
document_router = APIRouter(prefix="/v1/documents", tags=["documents"])


class ReindexRequest(BaseModel):
    chunk_template: str | None = Field(default=None, max_length=64)
    embedding_model: str | None = Field(default=None, max_length=128)


@collection_router.get("")
def list_documents(
    collection_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        documents = service.list_documents(collection_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    metrics.documents_total = service.count_documents()
    return ok([document.model_dump(mode="json") for document in documents])


@collection_router.post("", status_code=status.HTTP_201_CREATED)
def create_document(
    collection_id: str,
    payload: CreateDocumentInput,
    service: KnowledgeService = Depends(get_knowledge_service),
    metrics: MetricsRegistry = Depends(get_metrics),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        document = service.create_document(collection_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    metrics.documents_total = service.count_documents()
    return ok(document.model_dump(mode="json"), message="created")


@collection_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    collection_id: str,
    file: UploadFile = File(...),
    ingestion: IngestionService = Depends(get_ingestion_service),
    search_engine=Depends(get_search_engine),
    metrics: MetricsRegistry = Depends(get_metrics),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    data = await file.read()
    try:
        document = await ingestion.upload_document(
            collection_id=collection_id,
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            data=data,
            search_engine=search_engine,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    metrics.documents_total += 1
    return ok(document.model_dump(mode="json"), message="uploaded")


@collection_router.post("/bulk-upload", status_code=status.HTTP_201_CREATED)
async def bulk_upload_documents(
    collection_id: str,
    files: list[UploadFile] = File(...),
    ingestion: IngestionService = Depends(get_ingestion_service),
    search_engine=Depends(get_search_engine),
    metrics: MetricsRegistry = Depends(get_metrics),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    if len(files) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bulk upload accepts at most 20 files.")
    documents = []
    for file in files:
        data = await file.read()
        try:
            document = await ingestion.upload_document(
                collection_id=collection_id,
                filename=file.filename or "upload.bin",
                mime_type=file.content_type or "application/octet-stream",
                data=data,
                search_engine=search_engine,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        documents.append(document)
    metrics.documents_total += len(documents)
    return ok([document.model_dump(mode="json") for document in documents], message="uploaded")


@document_router.get("/{document_id}")
def get_document(
    document_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        document = service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(document.model_dump(mode="json"))


@document_router.get("/{document_id}/download-url")
def get_document_download_url(
    document_id: str,
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        url = ingestion.get_download_url(document_id=document_id, expires_seconds=600)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ok({"url": url, "expiresInSeconds": 600})


@document_router.get("/{document_id}/raw")
def get_document_raw(
    document_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    object_store: ObjectStorePort = Depends(get_object_store),
    principal=Depends(get_current_principal),
) -> Response:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        document = service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if document.object_key is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document has no stored object.")
    payload = object_store.get_object(key=document.object_key)
    return Response(
        content=payload,
        media_type=document.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.name}"'},
    )


@document_router.get("/{document_id}/text")
def get_document_text(
    document_id: str,
    ingestion: IngestionService = Depends(get_ingestion_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        text = ingestion.get_parsed_text(document_id=document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ok({"text": text})


_STATUS_PROGRESS = {
    "PENDING": (0, "pending"),
    "PARSING": (20, "parsing"),
    "PARSED": (40, "parsed"),
    "EMBEDDING": (60, "embedding"),
    "INDEXING": (80, "indexing"),
    "READY": (100, "ready"),
    "FAILED": (-1, "failed"),
    "CANCELLED": (-1, "cancelled"),
}


@document_router.get("/{document_id}/status")
def get_document_status(
    document_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        document = service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    progress_pct, stage = _STATUS_PROGRESS.get(document.status, (0, document.status.lower()))
    return ok(
        {
            "status": document.status,
            "progress_pct": progress_pct,
            "error_message": document.error_message,
            "stage": stage,
        }
    )


@document_router.post("/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_document(
    document_id: str,
    body: ReindexRequest | None = None,
    service: KnowledgeService = Depends(get_knowledge_service),
    queue: JobQueuePort = Depends(get_job_queue),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        document = service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if document.parsed_text_key is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document has no parsed text to re-index.")
    if body and (body.chunk_template or body.embedding_model):
        service.update_collection(
            document.collection_id,
            UpdateCollectionInput(
                chunk_template=body.chunk_template,
                embedding_model=body.embedding_model,
            ),
        )
    document = service.update_document_status(document_id, "PARSED")
    await queue.enqueue(
        job_name=INDEX_JOB_NAME,
        payload={"tenant_id": principal.tenant_id, "document_id": document_id},
    )
    return ok(document.model_dump(mode="json"), message="accepted")


@document_router.get("/{document_id}/graph")
def list_document_graph(
    document_id: str,
    entity: str | None = None,
    limit: int = 100,
    offset: int = 0,
    service: KnowledgeService = Depends(get_knowledge_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    try:
        service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    triples = service.list_graph_triples(
        document_id=document_id,
        entity=entity,
        limit=max(1, min(limit, 500)),
        offset=max(0, offset),
    )
    return ok([triple.model_dump(mode="json") for triple in triples])


class TagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


@document_router.put("/{document_id}/tags")
def set_document_tags(
    document_id: str,
    body: TagsRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        document = service.set_document_tags(document_id=document_id, tags=body.tags)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok(document.model_dump(mode="json"))


@collection_router.get("/by-tag/{tag}")
def list_documents_by_tag(
    collection_id: str,
    tag: str,
    service: KnowledgeService = Depends(get_knowledge_service),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_READ)
    documents = service.list_documents_by_tag(collection_id=collection_id, tag=tag)
    return ok([d.model_dump(mode="json") for d in documents])


@document_router.delete("/{document_id}")
def delete_document(
    document_id: str,
    ingestion: IngestionService = Depends(get_ingestion_service),
    search_engine=Depends(get_search_engine),
    principal=Depends(get_current_principal),
) -> dict:
    assert_permission(principal.role, Perm.DOCUMENTS_WRITE)
    try:
        ingestion.delete_document(document_id=document_id, search_engine=search_engine)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok({"deleted": document_id})
