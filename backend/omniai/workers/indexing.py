from __future__ import annotations

import logging
from datetime import datetime, timezone

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.config.settings import Settings
from omniai.plugins.chunk_templates import ChunkTemplateRegistry
from omniai.plugins.embedding_providers import build_embedding_provider
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.search_engine import IndexableChunk, SearchEnginePort

logger = logging.getLogger(__name__)

INDEX_JOB_NAME = "index_document"


async def index_document(
    *,
    settings: Settings,
    database: DatabaseManager,
    object_store: ObjectStorePort,
    search_engine: SearchEnginePort,
    chunk_templates: ChunkTemplateRegistry,
    tenant_id: str,
    document_id: str,
) -> None:
    with database.new_session() as session:
        store = SqlAlchemyKnowledgeStore(session, tenant_id)
        try:
            document = store.get_document(document_id)
        except KeyError:
            logger.warning("index_document: document %s not found", document_id)
            return
        if document.parsed_text_key is None:
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Cannot index a document with no parsed text.",
            )
            return

        try:
            collection = store.get_collection(document.collection_id)
        except KeyError:
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Document's collection has been deleted.",
            )
            return

        store.update_status(document_id=document_id, status="EMBEDDING")

        text = object_store.get_object(key=document.parsed_text_key).decode("utf-8")
        template = chunk_templates.get(collection.chunk_template)
        chunk_specs = template.chunk(
            text=text,
            document_metadata={
                "filename": document.name,
                "mime_type": document.mime_type,
            },
        )
        if not chunk_specs:
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Parser returned no extractable text.",
            )
            return

        chunks = store.replace_chunks(
            document_id=document_id,
            chunks=[{"text": spec.text, "metadata": spec.metadata} for spec in chunk_specs],
            template_name=template.name,
        )

        provider, model_name = build_embedding_provider(
            session=session,
            settings=settings,
            tenant_id=tenant_id,
            requested_model=collection.embedding_model,
        )
        try:
            vectors = await provider.embed(model=model_name, inputs=[c.text for c in chunks])
        except Exception as exc:
            logger.exception("index_document: embedding failed for %s", document_id)
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message=f"Embedding provider failed: {exc}",
            )
            return

        if len(vectors) != len(chunks) or any(not v for v in vectors):
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Embedding provider returned mismatched or empty vectors.",
            )
            return

        store.update_status(document_id=document_id, status="INDEXING")

        indexable = [
            IndexableChunk(
                chunk_id=chunks[i].id,
                document_id=document_id,
                collection_id=document.collection_id,
                text=chunks[i].text,
                vector=vectors[i],
                metadata={
                    **chunks[i].metadata,
                    "ordinal": chunks[i].ordinal,
                    "document_name": document.name,
                },
            )
            for i in range(len(chunks))
        ]
        search_engine.ensure_index(tenant_id=tenant_id, dim=len(vectors[0]))
        try:
            search_engine.delete_by_document(tenant_id=tenant_id, document_id=document_id)
            search_engine.upsert_chunks(tenant_id=tenant_id, chunks=indexable)
        except Exception as exc:
            logger.exception("index_document: search engine write failed for %s", document_id)
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message=f"Search engine write failed: {exc}",
            )
            return

        store.mark_chunks_indexed(document_id=document_id, indexed_at=datetime.now(timezone.utc))
        store.update_status(
            document_id=document_id,
            status="READY",
            page_count=document.page_count,
            parser_name=document.parser_name,
        )
        logger.info("index_document: %s ready (%d chunks, model=%s)", document_id, len(chunks), model_name)
