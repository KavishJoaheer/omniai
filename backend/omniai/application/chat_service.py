from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    CollectionRecord,
    ConversationRecord,
    MessageRecord,
)
from omniai.application.retrieval_service import (
    RetrievalRequest,
    RetrievalService,
)
from omniai.config.settings import Settings
from omniai.plugins.llm_providers.factory import build_llm_provider  # noqa: F401 (also used in _rewrite_query)
from omniai.ports.llm_provider import LlmMessage
from omniai.ports.search_engine import SearchHit
from omniai.security.secrets import SecretBox

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = (
    "You are Omni-AI, a helpful retrieval-augmented assistant. Answer questions using ONLY the "
    "provided context passages. Cite sources inline as [1], [2], ... where the bracketed number "
    "matches the passage's `[n]` marker. If the context does not contain the answer, say you "
    "don't know — do not invent facts."
)


@dataclass(slots=True)
class Citation:
    index: int
    chunk_id: str
    document_id: str
    document_name: str
    collection_id: str
    score: float
    snippet: str
    page_number: int | None = None


@dataclass(slots=True)
class ChatStreamEvent:
    kind: str  # "citations" | "graph" | "delta" | "done" | "error"
    delta: str | None = None
    citations: list[Citation] = field(default_factory=list)
    graph_lines: list[str] = field(default_factory=list)
    finish_reason: str | None = None
    error: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None


@dataclass(slots=True)
class ConversationSummary:
    id: str
    title: str
    model_provider: str | None
    model_name: str | None
    collection_ids: list[str]
    pinned: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class StoredMessage:
    id: str
    role: str
    content: str
    citations: list[dict]
    created_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json(text: str, default):
    try:
        return json.loads(text or "")
    except (json.JSONDecodeError, TypeError):
        return default


class ChatService:
    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        secret_box: SecretBox,
        retrieval_service: RetrievalService,
        tenant_id: str,
        user_id: str | None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._secret_box = secret_box
        self._retrieval = retrieval_service
        self._tenant_id = tenant_id
        self._user_id = user_id

    # ---- Conversations CRUD --------------------------------------------------

    def list_conversations(self) -> list[ConversationSummary]:
        statement = (
            select(ConversationRecord)
            .where(ConversationRecord.tenant_id == self._tenant_id)
            .order_by(ConversationRecord.pinned.desc(), ConversationRecord.updated_at.desc())
        )
        return [self._summary(record) for record in self._session.scalars(statement)]

    def create_conversation(
        self,
        *,
        title: str | None = None,
        system_prompt: str | None = None,
        collection_ids: list[str] | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
        top_k: int = 8,
        vector_weight: float = 0.6,
    ) -> ConversationRecord:
        record = ConversationRecord(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            title=title or "New conversation",
            system_prompt=system_prompt,
            collection_ids_json=json.dumps(collection_ids or []),
            model_provider=model_provider,
            model_name=model_name,
            temperature=str(temperature),
            top_k=top_k,
            vector_weight=str(vector_weight),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def get_conversation(self, conversation_id: str) -> ConversationRecord:
        record = self._session.scalar(
            select(ConversationRecord).where(
                ConversationRecord.id == conversation_id,
                ConversationRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Conversation not found.")
        return record

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        system_prompt: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> ConversationRecord:
        record = self.get_conversation(conversation_id)
        if title is not None:
            record.title = title.strip() or "New conversation"
        if pinned is not None:
            record.pinned = 1 if pinned else 0
        if system_prompt is not None:
            record.system_prompt = system_prompt
        if model_provider is not None:
            record.model_provider = model_provider
        if model_name is not None:
            record.model_name = model_name
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return record

    def delete_last_assistant_message(self, conversation_id: str) -> str | None:
        """Delete the most recent assistant message; return the prior user_text if any."""
        self.get_conversation(conversation_id)
        records = list(
            self._session.scalars(
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.created_at.desc())
                .limit(2)
            )
        )
        if not records or records[0].role != "assistant":
            return None
        last_user_text: str | None = None
        if len(records) > 1 and records[1].role == "user":
            last_user_text = records[1].content
            self._session.delete(records[1])
        self._session.delete(records[0])
        self._session.commit()
        return last_user_text

    def delete_conversation(self, conversation_id: str) -> None:
        record = self.get_conversation(conversation_id)
        # delete messages first
        for msg in self._session.scalars(
            select(MessageRecord).where(MessageRecord.conversation_id == record.id)
        ):
            self._session.delete(msg)
        self._session.delete(record)
        self._session.commit()

    def list_messages(self, conversation_id: str) -> list[StoredMessage]:
        self.get_conversation(conversation_id)
        statement = (
            select(MessageRecord)
            .where(MessageRecord.conversation_id == conversation_id)
            .order_by(MessageRecord.created_at.asc())
        )
        results: list[StoredMessage] = []
        for record in self._session.scalars(statement):
            results.append(
                StoredMessage(
                    id=record.id,
                    role=record.role,
                    content=record.content,
                    citations=_safe_json(record.citations_json, []),
                    created_at=record.created_at,
                )
            )
        return results

    # ---- Streaming chat ------------------------------------------------------

    async def stream_message(
        self,
        *,
        conversation_id: str | None,
        user_text: str,
        collection_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
        vector_weight: float | None = None,
        temperature: float | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        system_prompt: str | None = None,
        rerank: bool = True,
    ) -> AsyncIterator[ChatStreamEvent]:
        # Resolve or create the conversation
        if conversation_id:
            conversation = self.get_conversation(conversation_id)
        else:
            conversation = self.create_conversation(
                title=user_text[:60] or "New conversation",
                system_prompt=system_prompt,
                collection_ids=collection_ids,
                model_provider=model_provider,
                model_name=model_name,
                temperature=temperature if temperature is not None else 0.2,
                top_k=top_k if top_k is not None else 8,
                vector_weight=vector_weight if vector_weight is not None else 0.6,
            )

        # Resolve effective parameters (request overrides conversation defaults)
        eff_collections = collection_ids if collection_ids is not None else _safe_json(conversation.collection_ids_json, [])
        collection_defaults = self._load_collection_defaults(eff_collections)
        eff_top_k = top_k if top_k is not None else conversation.top_k
        eff_vector_weight = vector_weight if vector_weight is not None else float(conversation.vector_weight)
        eff_temperature = temperature if temperature is not None else float(conversation.temperature)
        eff_provider = model_provider or conversation.model_provider
        eff_model = model_name or conversation.model_name
        if top_k is None and collection_defaults.get("top_k") is not None:
            eff_top_k = int(collection_defaults["top_k"])
        if vector_weight is None and collection_defaults.get("vector_weight") is not None:
            eff_vector_weight = float(collection_defaults["vector_weight"])
        eff_system = (
            system_prompt
            if system_prompt is not None
            else (conversation.system_prompt or collection_defaults.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)
        )

        # Persist the incoming user message
        user_message = MessageRecord(
            tenant_id=self._tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=user_text,
            citations_json="[]",
            usage_json="{}",
        )
        self._session.add(user_message)
        self._session.commit()

        # For multi-turn: rewrite the query if there's prior history
        history_for_rewrite = self._load_recent_history(conversation.id, limit=4)
        search_query = await self._rewrite_query(user_text, history_for_rewrite)

        # Retrieve context
        retrieval_response = await self._retrieval.retrieve(
            RetrievalRequest(
                query=search_query,
                top_k=eff_top_k,
                vector_weight=eff_vector_weight,
                collection_ids=eff_collections or None,
                document_ids=document_ids,
                rerank=rerank,
            )
        )
        citations = self._build_citations(retrieval_response.hits)

        # Emit citations event up-front so the UI can render placeholders
        yield ChatStreamEvent(
            kind="citations",
            citations=citations,
            conversation_id=conversation.id,
        )

        # Emit graph_context event for the UI's knowledge-graph panel
        seen_graph: set[str] = set()
        graph_lines: list[str] = []
        for hit in retrieval_response.hits:
            for line in (hit.metadata or {}).get("graph_context", []) or []:
                if line and line not in seen_graph:
                    seen_graph.add(line)
                    graph_lines.append(line)
        if graph_lines:
            yield ChatStreamEvent(
                kind="graph",
                graph_lines=graph_lines[:15],
                conversation_id=conversation.id,
            )

        # Build prompt and call LLM
        history = self._load_recent_history(conversation.id, limit=10)
        prompt_messages = self._build_prompt(
            system_prompt=eff_system,
            history=history,
            user_text=user_text,
            citations=citations,
            hits=retrieval_response.hits,
        )

        provider, resolved_model = build_llm_provider(
            session=self._session,
            settings=self._settings,
            secret_box=self._secret_box,
            tenant_id=self._tenant_id,
            requested_model=eff_model,
            requested_provider=eff_provider,
        )

        accumulated = []
        finish_reason: str | None = None
        try:
            async for chunk in provider.stream_chat(
                model=resolved_model,
                messages=prompt_messages,
                temperature=eff_temperature,
            ):
                if chunk.delta:
                    accumulated.append(chunk.delta)
                    yield ChatStreamEvent(kind="delta", delta=chunk.delta)
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
        except Exception as exc:  # pragma: no cover - surfaced to client
            logger.exception("LLM provider failed")
            yield ChatStreamEvent(kind="error", error=f"LLM provider failed: {exc}")
            return

        full_text = "".join(accumulated).strip()

        # Estimate token usage (chars / 4 ≈ tokens; good enough for cost tracking)
        prompt_chars = sum(len(m.content) for m in prompt_messages)
        prompt_tokens_est = max(1, prompt_chars // 4)
        completion_tokens_est = max(1, len(full_text) // 4)

        # Persist the assistant message
        assistant_message = MessageRecord(
            tenant_id=self._tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=full_text,
            citations_json=json.dumps([_citation_to_dict(c) for c in citations]),
            usage_json=json.dumps(
                {
                    "model": resolved_model,
                    "provider": provider.kind,
                    "finish_reason": finish_reason,
                    "prompt_tokens": prompt_tokens_est,
                    "completion_tokens": completion_tokens_est,
                }
            ),
        )
        self._session.add(assistant_message)
        # Refresh updated_at on the conversation
        conversation.updated_at = utc_now()
        self._session.commit()

        # Record token usage for cost tracking (M16) — fire-and-forget
        try:
            from omniai.application.observability_service import ObservabilityService
            ObservabilityService(self._session, self._settings).record_token_usage(
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                conversation_id=conversation.id,
                model_provider=provider.kind,
                model_name=resolved_model,
                prompt_tokens=prompt_tokens_est,
                completion_tokens=completion_tokens_est,
            )
        except Exception:
            logger.debug("token usage recording failed (non-fatal)", exc_info=True)

        yield ChatStreamEvent(
            kind="done",
            finish_reason=finish_reason or "stop",
            conversation_id=conversation.id,
            message_id=assistant_message.id,
        )

    # ---- Internal helpers ----------------------------------------------------

    async def _rewrite_query(self, user_text: str, history: list[LlmMessage]) -> str:
        """Rewrite a follow-up question into a standalone search query using the LLM.

        Only rewrites when there is prior history — otherwise the user text is returned as-is.
        Keeps it fast by using a small system prompt and limiting output tokens.
        """
        prior = [m for m in history if m.role in ("user", "assistant")]
        if not prior:
            return user_text

        try:
            provider, model = build_llm_provider(
                session=self._session,
                settings=self._settings,
                secret_box=self._secret_box,
                tenant_id=self._tenant_id,
            )
            rewrite_messages = [
                LlmMessage(
                    role="system",
                    content=(
                        "You are a query rewriter. Given a conversation history and a follow-up question, "
                        "rewrite the follow-up question into a single, self-contained search query that captures "
                        "the full intent. Output ONLY the rewritten query — no explanation, no quotes."
                    ),
                ),
                *prior[-4:],
                LlmMessage(
                    role="user",
                    content=f"Follow-up question: {user_text}\nRewritten standalone query:",
                ),
            ]
            chunks: list[str] = []
            async for chunk in provider.stream_chat(model=model, messages=rewrite_messages, temperature=0.0, max_tokens=80):
                if chunk.delta:
                    chunks.append(chunk.delta)
                if chunk.finish_reason:
                    break
            rewritten = "".join(chunks).strip().strip('"').strip()
            return rewritten if rewritten else user_text
        except Exception:
            return user_text

    def _summary(self, record: ConversationRecord) -> ConversationSummary:
        return ConversationSummary(
            id=record.id,
            title=record.title,
            model_provider=record.model_provider,
            model_name=record.model_name,
            collection_ids=_safe_json(record.collection_ids_json, []),
            pinned=bool(record.pinned),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _load_recent_history(self, conversation_id: str, *, limit: int) -> list[LlmMessage]:
        # Pull the last N messages, oldest first
        statement = (
            select(MessageRecord)
            .where(MessageRecord.conversation_id == conversation_id)
            .order_by(MessageRecord.created_at.desc())
            .limit(limit)
        )
        records = list(self._session.scalars(statement))
        records.reverse()
        return [LlmMessage(role=r.role, content=r.content) for r in records if r.role in ("user", "assistant")]

    def _load_collection_defaults(self, collection_ids: list[str]) -> dict:
        if not collection_ids:
            return {}
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.tenant_id == self._tenant_id,
                CollectionRecord.id.in_(collection_ids),
                CollectionRecord.system_prompt.is_not(None),
            )
        )
        if record is not None:
            return {
                "system_prompt": record.system_prompt,
                "top_k": record.top_k,
                "vector_weight": record.vector_weight,
            }
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.tenant_id == self._tenant_id,
                CollectionRecord.id.in_(collection_ids),
            )
        )
        if record is None:
            return {}
        return {
            "top_k": record.top_k,
            "vector_weight": record.vector_weight,
        }

    def _build_citations(self, hits: list[SearchHit]) -> list[Citation]:
        citations: list[Citation] = []
        for index, hit in enumerate(hits, start=1):
            metadata = hit.metadata or {}
            document_name = metadata.get("document_name") or metadata.get("filename") or "Unknown"
            page_number = metadata.get("page_number")
            citations.append(
                Citation(
                    index=index,
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    document_name=str(document_name),
                    collection_id=hit.collection_id,
                    score=hit.score,
                    snippet=hit.snippet or hit.text[:280],
                    page_number=int(page_number) if isinstance(page_number, (int, float)) else None,
                )
            )
        return citations

    def _build_prompt(
        self,
        *,
        system_prompt: str,
        history: list[LlmMessage],
        user_text: str,
        citations: list[Citation],
        hits: list[SearchHit] | None = None,
    ) -> list[LlmMessage]:
        if citations:
            context_lines = ["You have access to these context passages:"]
            for c in citations:
                snippet = c.snippet.replace("\n", " ").strip()
                source_label = c.document_name
                if c.page_number is not None:
                    source_label = f"{c.document_name}, p.{c.page_number}"
                context_lines.append(f"[{c.index}] (source: {source_label}) {snippet}")
            context_block = "\n".join(context_lines)
        else:
            context_block = "No retrieved context is available for this question."

        graph_block = ""
        if hits:
            seen_lines: set[str] = set()
            graph_lines: list[str] = []
            for hit in hits:
                for line in (hit.metadata or {}).get("graph_context", []) or []:
                    if line and line not in seen_lines:
                        seen_lines.add(line)
                        graph_lines.append(line)
            if graph_lines:
                graph_block = (
                    "\n\nRelated facts from the knowledge graph (use to ground your answer; "
                    "do not cite these as separate sources):\n"
                    + "\n".join(f"- {line}" for line in graph_lines[:15])
                )

        full_system = f"{system_prompt}\n\n{context_block}{graph_block}"
        messages: list[LlmMessage] = [LlmMessage(role="system", content=full_system)]
        # include prior turns but exclude the most recent user message we just inserted
        for msg in history:
            if msg.role == "user" and msg.content == user_text:
                continue
            messages.append(msg)
        messages.append(LlmMessage(role="user", content=user_text))
        return messages


def _citation_to_dict(c: Citation) -> dict:
    return {
        "index": c.index,
        "chunk_id": c.chunk_id,
        "document_id": c.document_id,
        "document_name": c.document_name,
        "collection_id": c.collection_id,
        "score": c.score,
        "snippet": c.snippet,
        "page_number": c.page_number,
    }
