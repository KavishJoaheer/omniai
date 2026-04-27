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
    created_at: datetime
    updated_at: datetime


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
    top_k: int | None = Field(default=None, ge=1, le=50)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    model_provider: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None


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
        created_at=summary.created_at,
        updated_at=summary.updated_at,
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
                top_k=body.top_k,
                vector_weight=body.vector_weight,
                temperature=body.temperature,
                model_provider=body.model_provider,
                model_name=body.model_name,
                system_prompt=body.system_prompt,
            ):
                payload: dict = {"kind": event.kind}
                if event.kind == "citations":
                    payload["citations"] = [_citation_to_dict(c) for c in event.citations]
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
