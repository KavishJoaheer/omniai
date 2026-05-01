from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from omniai.application.chat_service import ChatService, _citation_to_dict
from omniai.interfaces.http.deps import get_chat_service

router = APIRouter(prefix="/v1", tags=["chat"])


class ConversationOut(BaseModel):
    id: str
    title: str
    model_provider: str | None
    model_name: str | None
    collection_ids: list[str]
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    system_prompt: str | None = None
    model_provider: str | None = None
    model_name: str | None = None


class RegenerateRequest(BaseModel):
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_provider: str | None = None
    model_name: str | None = None
    rerank: bool = True


class CreateConversationRequest(BaseModel):
    title: str | None = None
    system_prompt: str | None = None
    collection_ids: list[str] | None = None
    model_provider: str | None = None
    model_name: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_k: int = Field(default=8, ge=1, le=50)
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict]
    created_at: datetime


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    collection_ids: list[str] | None = None
    document_ids: list[str] | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_provider: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    rerank: bool = True


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(chat_service: ChatService = Depends(get_chat_service)) -> list[ConversationOut]:
    summaries = chat_service.list_conversations()
    return [
        ConversationOut(
            id=s.id,
            title=s.title,
            model_provider=s.model_provider,
            model_name=s.model_name,
            collection_ids=s.collection_ids,
            pinned=s.pinned,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in summaries
    ]


@router.post("/conversations", response_model=ConversationOut)
def create_conversation(
    body: CreateConversationRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ConversationOut:
    record = chat_service.create_conversation(
        title=body.title,
        system_prompt=body.system_prompt,
        collection_ids=body.collection_ids,
        model_provider=body.model_provider,
        model_name=body.model_name,
        temperature=body.temperature,
        top_k=body.top_k,
        vector_weight=body.vector_weight,
    )
    summary = chat_service._summary(record)
    return ConversationOut(
        id=summary.id,
        title=summary.title,
        model_provider=summary.model_provider,
        model_name=summary.model_name,
        collection_ids=summary.collection_ids,
        pinned=summary.pinned,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ConversationOut:
    try:
        record = chat_service.update_conversation(
            conversation_id,
            title=body.title,
            pinned=body.pinned,
            system_prompt=body.system_prompt,
            model_provider=body.model_provider,
            model_name=body.model_name,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    summary = chat_service._summary(record)
    return ConversationOut(
        id=summary.id,
        title=summary.title,
        model_provider=summary.model_provider,
        model_name=summary.model_name,
        collection_ids=summary.collection_ids,
        pinned=summary.pinned,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.post("/conversations/{conversation_id}/regenerate")
async def regenerate_last_message(
    conversation_id: str,
    body: RegenerateRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    user_text = chat_service.delete_last_assistant_message(conversation_id)
    if user_text is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No assistant message to regenerate.",
        )

    async def event_stream():
        try:
            async for event in chat_service.stream_message(
                conversation_id=conversation_id,
                user_text=user_text,
                temperature=body.temperature,
                model_provider=body.model_provider,
                model_name=body.model_name,
                rerank=body.rerank,
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


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> list[MessageOut]:
    try:
        messages = chat_service.list_messages(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=m.citations,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    try:
        chat_service.delete_conversation(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"deleted": conversation_id}


# ── M18: Conversation export ─────────────────────────────────────────────────

from fastapi.responses import Response as HttpResponse  # noqa: E402  (local import avoids circular at top)


@router.get("/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: str,
    format: str = "json",  # "json" | "markdown"
    chat_service: ChatService = Depends(get_chat_service),
) -> HttpResponse:
    """Export a full conversation as JSON or Markdown.

    - ``format=json`` → ``application/json``; includes all message metadata.
    - ``format=markdown`` → ``text/markdown``; human-readable chat transcript.
    """
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="format must be 'json' or 'markdown'.")
    try:
        conv = chat_service.get_conversation(conversation_id)
        messages = chat_service.list_messages(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in conv.title)[:60]

    if format == "json":
        payload = {
            "id": conv.id,
            "title": conv.title,
            "model_provider": conv.model_provider,
            "model_name": conv.model_name,
            "collection_ids": json.loads(conv.collection_ids_json or "[]"),
            "created_at": conv.created_at.isoformat() if hasattr(conv.created_at, "isoformat") else str(conv.created_at),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "citations": m.citations,
                    "created_at": m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at),
                }
                for m in messages
            ],
        }
        body_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return HttpResponse(
            content=body_bytes,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.json"'},
        )
    else:
        lines = [f"# {conv.title}", ""]
        if conv.model_provider and conv.model_name:
            lines.append(f"*Model: {conv.model_provider}/{conv.model_name}*")
            lines.append("")
        for m in messages:
            role_label = "**You**" if m.role == "user" else "**Assistant**"
            ts = m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else str(m.created_at)
            lines.append(f"{role_label} _{ts}_")
            lines.append("")
            lines.append(m.content)
            if m.citations:
                lines.append("")
                lines.append("*Sources:*")
                for c in m.citations:
                    if isinstance(c, dict):
                        lines.append(f"  - [{c.get('document_name', 'doc')}] score={c.get('score', ''):.3f}" if isinstance(c.get('score'), float) else f"  - {c.get('document_name', 'doc')}")
            lines.append("")
            lines.append("---")
            lines.append("")
        body_bytes = "\n".join(lines).encode("utf-8")
        return HttpResponse(
            content=body_bytes,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.md"'},
        )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    if not body.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message is required.")

    async def event_stream():
        try:
            async for event in chat_service.stream_message(
                conversation_id=body.conversation_id,
                user_text=body.message,
                collection_ids=body.collection_ids,
                document_ids=body.document_ids,
                top_k=body.top_k,
                vector_weight=body.vector_weight,
                temperature=body.temperature,
                model_provider=body.model_provider,
                model_name=body.model_name,
                system_prompt=body.system_prompt,
                rerank=body.rerank,
            ):
                payload: dict = {"kind": event.kind}
                if event.kind == "citations":
                    payload["citations"] = [_citation_to_dict(c) for c in event.citations]
                    if event.conversation_id:
                        payload["conversation_id"] = event.conversation_id
                elif event.kind == "graph":
                    payload["graph_lines"] = event.graph_lines
                    if event.conversation_id:
                        payload["conversation_id"] = event.conversation_id
                elif event.kind == "delta":
                    payload["delta"] = event.delta or ""
                elif event.kind == "done":
                    payload["finish_reason"] = event.finish_reason
                    payload["conversation_id"] = event.conversation_id
                    payload["message_id"] = event.message_id
                elif event.kind == "error":
                    payload["error"] = event.error
                yield f"data: {json.dumps(payload)}\n\n"
        except KeyError as exc:
            yield f"data: {json.dumps({'kind': 'error', 'error': str(exc)})}\n\n"
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
