from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from omniai.adapters.relational.sqlalchemy.models import ChunkRecord
from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.adapters.relational.sqlalchemy.session import DatabaseManager
from omniai.config.settings import Settings
from omniai.domain.knowledge.models import Chunk
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

        all_chunks = store.replace_chunks(
            document_id=document_id,
            chunks=[
                {
                    "text": spec.text,
                    "metadata": spec.metadata,
                    "is_indexable": spec.metadata.get("is_indexable", True),
                }
                for spec in chunk_specs
            ],
            template_name=template.name,
        )

        # For small-to-big templates, wire up parent_chunk_id on child chunks.
        _link_parent_chunks(session, all_chunks)

        # Reload chunks so parent_chunk_id values are fresh from the DB
        all_chunks = store.list_chunks(document_id=document_id)

        # Only embed + index chunks that are marked indexable (children, or all for flat templates)
        indexable_chunks = [c for c in all_chunks if c.is_indexable]
        if not indexable_chunks:
            # All chunks are parents — fall back to indexing everything
            indexable_chunks = all_chunks

        provider, model_name = build_embedding_provider(
            session=session,
            settings=settings,
            tenant_id=tenant_id,
            requested_model=collection.embedding_model,
        )
        try:
            vectors = await provider.embed(model=model_name, inputs=[c.text for c in indexable_chunks])
        except Exception as exc:
            logger.exception("index_document: embedding failed for %s", document_id)
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message=f"Embedding provider failed: {exc}",
            )
            return

        if len(vectors) != len(indexable_chunks) or any(not v for v in vectors):
            store.update_status(
                document_id=document_id,
                status="FAILED",
                error_message="Embedding provider returned mismatched or empty vectors.",
            )
            return

        store.update_status(document_id=document_id, status="INDEXING")

        to_index = [
            IndexableChunk(
                chunk_id=indexable_chunks[i].id,
                document_id=document_id,
                collection_id=document.collection_id,
                text=indexable_chunks[i].text,
                vector=vectors[i],
                metadata={
                    **indexable_chunks[i].metadata,
                    "ordinal": indexable_chunks[i].ordinal,
                    "document_name": document.name,
                    "parent_chunk_id": indexable_chunks[i].parent_chunk_id or "",
                },
            )
            for i in range(len(indexable_chunks))
        ]
        search_engine.ensure_index(tenant_id=tenant_id, dim=len(vectors[0]))
        try:
            search_engine.delete_by_document(tenant_id=tenant_id, document_id=document_id)
            search_engine.upsert_chunks(tenant_id=tenant_id, chunks=to_index)
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
        logger.info(
            "index_document: %s ready (%d chunks, %d indexed, model=%s)",
            document_id,
            len(all_chunks),
            len(indexable_chunks),
            model_name,
        )


def _link_parent_chunks(session, all_chunks: list[Chunk]) -> None:
    """For small-to-big templates, set parent_chunk_id on child chunks.

    Parent chunks carry metadata['chunk_kind'] == 'parent' and metadata['parent_index'] = N.
    Child chunks carry metadata['chunk_kind'] == 'child' and metadata['parent_index'] = N.
    We look up parent chunks by parent_index and write the parent chunk's DB id into
    the child's parent_chunk_id column.
    """
    has_hierarchy = any(c.metadata.get("chunk_kind") == "parent" for c in all_chunks)
    if not has_hierarchy:
        return

    # Build parent_index -> chunk.id map for parent chunks
    parent_id_by_index: dict[int, str] = {}
    for chunk in all_chunks:
        if chunk.metadata.get("chunk_kind") == "parent":
            idx = chunk.metadata.get("parent_index")
            if idx is not None:
                parent_id_by_index[idx] = chunk.id

    if not parent_id_by_index:
        return

    # Update child records in bulk
    for chunk in all_chunks:
        if chunk.metadata.get("chunk_kind") == "child":
            parent_idx = chunk.metadata.get("parent_index")
            parent_id = parent_id_by_index.get(parent_idx) if parent_idx is not None else None
            if parent_id:
                session.execute(
                    update(ChunkRecord)
                    .where(ChunkRecord.id == chunk.id)
                    .values(parent_chunk_id=parent_id)
                )
    session.commit()
