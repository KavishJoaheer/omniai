from __future__ import annotations

import io
import logging

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.application.ingestion_service import build_parsed_text_key
from omniai.plugins.parsers import ParserRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort

logger = logging.getLogger(__name__)


INDEX_JOB_NAME = "index_document"


async def parse_document(
    *,
    database: DatabaseManager,
    object_store: ObjectStorePort,
    parsers: ParserRegistry,
    queue: JobQueuePort,
    tenant_id: str,
    document_id: str,
) -> None:
    with database.new_session() as session:
        store = SqlAlchemyKnowledgeStore(session, tenant_id)
        try:
            document = store.get_document(document_id)
        except KeyError:
            logger.warning("parse_document: document %s not found", document_id)
            return

        if document.object_key is None:
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Document has no stored object.",
            )
            return

        store.update_status(document_id=document_id, status="PARSING")
        parser = parsers.resolve(mime_type=document.mime_type, filename=document.name)
        if parser is None:
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message=f"No parser available for {document.mime_type or document.name}.",
            )
            return

        try:
            data = object_store.get_object(key=document.object_key)
            result = parser.parse(data=data, filename=document.name)
        except Exception as exc:
            logger.exception("parse_document: parser %s failed for %s", parser.name, document_id)
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message=f"Parser {parser.name!r} failed: {exc}",
            )
            return

        parsed_text_key = build_parsed_text_key(
            tenant_id=tenant_id,
            collection_id=document.collection_id,
            document_id=document.id,
        )
        text_bytes = result.text.encode("utf-8")
        object_store.put_object(
            key=parsed_text_key,
            data=io.BytesIO(text_bytes),
            content_type="text/plain; charset=utf-8",
            size=len(text_bytes),
        )

        store.update_status(
            document_id=document_id,
            status="PARSED",
            parsed_text_key=parsed_text_key,
            page_count=result.page_count,
            parser_name=parser.name,
        )
        logger.info("parse_document: %s parsed (parser=%s, %d chars) — queuing index", document_id, parser.name, len(result.text))

    await queue.enqueue(
        job_name=INDEX_JOB_NAME,
        payload={"tenant_id": tenant_id, "document_id": document_id},
    )
