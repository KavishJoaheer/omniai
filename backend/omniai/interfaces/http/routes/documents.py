from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from omniai.application.ingestion_service import IngestionService
from omniai.application.services import CreateDocumentInput, KnowledgeService
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_ingestion_service,
    get_knowledge_service,
    get_metrics,
    get_object_store,
    get_search_engine,
)
from omniai.interfaces.http.envelope import ok
from omniai.observability.metrics import MetricsRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.security.permissions import Perm, assert_permission

collection_router = APIRouter(prefix="/v1/collections/{collection_id}/documents", tags=["documents"])
document_router = APIRouter(prefix="/v1/documents", tags=["documents"])


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
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    metrics.documents_total += 1
    return ok(document.model_dump(mode="json"), message="uploaded")


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
