from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.application.retrieval_service import RetrievalRequest, RetrievalService
from omniai.interfaces.http.deps import (
    get_current_principal,
    get_db_session,
    get_retrieval_service,
)

router = APIRouter(prefix="/v1", tags=["retrieval"])


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=50)
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    collection_ids: list[str] | None = None
    embedding_model: str = "nomic-embed-text"


class HitOut(BaseModel):
    chunk_id: str
    document_id: str
    collection_id: str
    score: float
    text: str
    snippet: str
    metadata: dict


class RetrieveResponse(BaseModel):
    hits: list[HitOut]
    embedding_model: str
    vector_weight: float


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(
    body: RetrieveRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> RetrieveResponse:
    result = await retrieval_service.retrieve(
        RetrievalRequest(
            query=body.query,
            top_k=body.top_k,
            vector_weight=body.vector_weight,
            collection_ids=body.collection_ids,
            embedding_model=body.embedding_model,
        )
    )
    hits = [
        HitOut(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            collection_id=h.collection_id,
            score=h.score,
            text=h.text,
            snippet=h.snippet,
            metadata=h.metadata,
        )
        for h in result.hits
    ]
    return RetrieveResponse(
        hits=hits,
        embedding_model=result.embedding_model,
        vector_weight=result.vector_weight,
    )


class ChunkOut(BaseModel):
    id: str
    ordinal: int
    text: str
    char_count: int
    token_count: int
    template_name: str
    metadata: dict
    indexed_at: str | None


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkOut])
def list_chunks(
    document_id: str,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> list[ChunkOut]:
    store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    try:
        store.get_document(document_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    chunks = store.list_chunks(document_id=document_id)
    return [
        ChunkOut(
            id=c.id,
            ordinal=c.ordinal,
            text=c.text,
            char_count=c.char_count,
            token_count=c.token_count,
            template_name=c.template_name,
            metadata=c.metadata,
            indexed_at=c.indexed_at.isoformat() if c.indexed_at else None,
        )
        for c in chunks
    ]
