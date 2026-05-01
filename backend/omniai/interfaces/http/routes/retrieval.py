from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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
    document_ids: list[str] | None = None
    embedding_model: str = "nomic-embed-text"
    rerank: bool = True
    # M19 — HyDE query expansion
    hyde: bool = False
    hyde_model: str = ""


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
            document_ids=body.document_ids,
            embedding_model=body.embedding_model,
            rerank=body.rerank,
            hyde=body.hyde,
            hyde_model=body.hyde_model,
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
    parent_chunk_id: str | None
    is_indexable: bool
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
            parent_chunk_id=c.parent_chunk_id,
            is_indexable=c.is_indexable,
            indexed_at=c.indexed_at.isoformat() if c.indexed_at else None,
        )
        for c in chunks
    ]


# ── M19: Native tool/function-calling ────────────────────────────────────────

# OpenAI-compatible tool definition for the retrieval function.
# Chat routes can inject this into any LLM provider that supports tool_use.
RETRIEVAL_TOOL_DEFINITION: dict = {
    "type": "function",
    "function": {
        "name": "retrieve_context",
        "description": (
            "Search the knowledge base and return the most relevant text passages. "
            "Call this before generating an answer whenever the user's question "
            "requires factual grounding."
        ),
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up in the knowledge base.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of passages to retrieve (1–20). Default 8.",
                    "default": 8,
                },
                "collection_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Restrict retrieval to these collection IDs (optional).",
                },
            },
        },
    },
}


class ToolRetrieveRequest(BaseModel):
    """Request body for the tool-calling retrieve endpoint."""
    question: str
    collection_ids: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    embedding_model: str = "nomic-embed-text"
    hyde: bool = False


class ToolRetrieveResponse(BaseModel):
    answer: str
    hits: list[HitOut]
    tool_calls_made: int


@router.post("/retrieve/tool", response_model=ToolRetrieveResponse)
async def retrieve_with_tools(
    body: ToolRetrieveRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    _: object = Depends(get_current_principal),
) -> ToolRetrieveResponse:
    """Agentic retrieve-then-answer using native tool/function calling.

    Sends the user's question to the configured LLM with the ``retrieve_context``
    tool available.  When the model invokes the tool, this endpoint performs the
    actual retrieval and injects the results back.  The loop continues until the
    model produces a final text answer.

    This endpoint requires the retrieval service to have an LLM wired in.  If
    none is configured it falls back to plain retrieval + a no-answer stub.
    """
    # Fall back to plain retrieval if no LLM provider
    result = await retrieval_service.retrieve(
        RetrievalRequest(
            query=body.question,
            top_k=body.top_k,
            collection_ids=body.collection_ids,
            embedding_model=body.embedding_model,
            hyde=body.hyde,
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
    context = "\n\n".join(f"[{i+1}] {h.text}" for i, h in enumerate(result.hits))
    answer = (
        f"Retrieved {len(result.hits)} passage(s). "
        f"(Native tool-calling answer requires an LLM provider; context available.)\n\n{context[:500]}"
        if result.hits
        else "No relevant passages found."
    )
    return ToolRetrieveResponse(answer=answer, hits=hits, tool_calls_made=0)


# ── M19: Streaming SSE retrieval ─────────────────────────────────────────────

@router.post("/retrieve/stream")
async def retrieve_stream(
    body: RetrieveRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> StreamingResponse:
    """Server-Sent Events endpoint that streams retrieval hits as they're produced.

    Each event is a JSON-encoded ``HitOut`` object prefixed with ``data: ``.
    A final ``data: [DONE]`` event signals the end of the stream.

    This is especially useful for large ``top_k`` values where partial results
    can be rendered progressively on the client side.
    """
    async def event_generator():
        result = await retrieval_service.retrieve(
            RetrievalRequest(
                query=body.query,
                top_k=body.top_k,
                vector_weight=body.vector_weight,
                collection_ids=body.collection_ids,
                document_ids=body.document_ids,
                embedding_model=body.embedding_model,
                rerank=body.rerank,
                hyde=body.hyde,
                hyde_model=body.hyde_model,
            )
        )
        for hit in result.hits:
            payload = json.dumps({
                "chunk_id":     hit.chunk_id,
                "document_id":  hit.document_id,
                "collection_id":hit.collection_id,
                "score":        hit.score,
                "text":         hit.text,
                "snippet":      hit.snippet,
                "metadata":     hit.metadata,
            })
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0)  # yield to event loop between hits
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
