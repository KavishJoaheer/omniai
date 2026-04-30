from __future__ import annotations

import json
import logging
import re

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.config.settings import Settings
from omniai.plugins.llm_providers.factory import build_llm_provider
from omniai.ports.llm_provider import LlmMessage
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.search_engine import SearchEnginePort
from omniai.security.secrets import SecretBox

logger = logging.getLogger(__name__)

GRAPH_JOB_NAME = "extract_graph"

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


async def extract_graph(
    *,
    settings: Settings,
    database: DatabaseManager,
    object_store: ObjectStorePort,
    search_engine: SearchEnginePort,
    secret_box: SecretBox,
    tenant_id: str,
    document_id: str,
) -> None:
    del search_engine
    with database.new_session() as session:
        store = SqlAlchemyKnowledgeStore(session, tenant_id)
        try:
            document = store.get_document(document_id)
        except KeyError:
            logger.warning("extract_graph: document %s not found", document_id)
            return
        if document.parsed_text_key is None:
            return

        try:
            parsed_text = object_store.get_object(key=document.parsed_text_key).decode("utf-8")
        except Exception as exc:
            logger.warning("extract_graph: cannot read parsed text for %s: %s", document_id, exc)
            return

        chunks = store.list_chunks(document_id=document_id)
        chunk_texts = [chunk.text for chunk in chunks if chunk.is_indexable and chunk.text.strip()]
        if not chunk_texts:
            chunk_texts = _fallback_chunks(parsed_text)
        if not chunk_texts:
            store.replace_graph_triples(document_id=document_id, triples=[])
            return

        try:
            provider, model = build_llm_provider(
                session=session,
                settings=settings,
                secret_box=secret_box,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning("extract_graph: no LLM provider available for %s: %s", document_id, exc)
            return

        triples: list[dict] = []
        for text in chunk_texts:
            triples.extend(await _extract_chunk_triples(provider=provider, model=model, text=text))

        deduped = _dedupe_triples(triples)
        stored = store.replace_graph_triples(document_id=document_id, triples=deduped)
        logger.info("extract_graph: stored %d triples for %s", len(stored), document_id)


async def _extract_chunk_triples(*, provider, model: str, text: str) -> list[dict]:
    prompt = (
        "Extract all factual relationships from this text as JSON triples.\n"
        "Each triple: {\"subject\": string, \"predicate\": string, \"object\": string, \"confidence\": 0-1}\n"
        "Output ONLY a JSON array.\n\n"
        f"Text:\n{text[:5000]}"
    )
    try:
        parts: list[str] = []
        async for chunk in provider.stream_chat(
            model=model,
            messages=[LlmMessage(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=1200,
        ):
            if chunk.delta:
                parts.append(chunk.delta)
            if chunk.finish_reason:
                break
    except Exception as exc:
        logger.warning("extract_graph: LLM extraction failed: %s", exc)
        return []

    return _parse_triples("".join(parts))


def _parse_triples(raw: str) -> list[dict]:
    cleaned = _FENCE_RE.sub("", raw.strip()).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if match is None:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _dedupe_triples(triples: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    results: list[dict] = []
    for triple in triples:
        subject = str(triple.get("subject") or "").strip()
        predicate = str(triple.get("predicate") or "").strip()
        object_value = str(triple.get("object") or triple.get("object_") or "").strip()
        key = (subject.lower(), predicate.lower(), object_value.lower())
        if not subject or not predicate or not object_value or key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "subject": subject,
                "predicate": predicate,
                "object": object_value,
                "confidence": triple.get("confidence", 1.0),
            }
        )
    return results


def _fallback_chunks(text: str, *, size: int = 2500) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    return [normalized[index : index + size] for index in range(0, len(normalized), size)]
