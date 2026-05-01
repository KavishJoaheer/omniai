from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    AgentRecord,
    AgentRunRecord,
    ChunkRecord,
    CollectionMembershipRecord,
    CollectionRecord,
    ConnectorRecord,
    DeploymentRecord,
    DocumentRecord,
    GraphTripleRecord,
    TenantRecord,
)
from omniai.application.store import KnowledgeStore
from omniai.domain.agents.models import Agent, AgentRun
from omniai.domain.connectors.models import Connector
from omniai.domain.deployments.models import Deployment
from omniai.domain.knowledge.models import (
    Chunk,
    Collection,
    CollectionMembership,
    Document,
    GraphTriple,
    utc_now,
)
from omniai.ports.agents import AgentStorePort
from omniai.ports.connectors import ConnectorStorePort
from omniai.ports.deployments import DeploymentStorePort


def ensure_tenant(session: Session, *, slug: str, name: str) -> TenantRecord:
    tenant = session.scalar(select(TenantRecord).where(TenantRecord.slug == slug))
    if tenant is not None:
        return tenant

    tenant = TenantRecord(slug=slug, name=name)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


class SqlAlchemyKnowledgeStore(KnowledgeStore):
    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def list_collections(self) -> list[Collection]:
        statement = (
            select(CollectionRecord)
            .where(CollectionRecord.tenant_id == self._tenant_id)
            .order_by(CollectionRecord.created_at.asc())
        )
        return [self._to_collection(record) for record in self._session.scalars(statement)]

    def create_collection(
        self,
        *,
        name: str,
        description: str | None,
        embedding_model: str,
        chunk_template: str,
        system_prompt: str | None = None,
        top_k: int = 8,
        vector_weight: float = 0.6,
    ) -> Collection:
        duplicate = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.tenant_id == self._tenant_id,
                func.lower(CollectionRecord.name) == name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("A collection with that name already exists.")

        record = CollectionRecord(
            tenant_id=self._tenant_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            chunk_template=chunk_template,
            system_prompt=system_prompt,
            top_k=top_k,
            vector_weight=vector_weight,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_collection(record)

    def get_collection(self, collection_id: str) -> Collection:
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Collection not found.")
        return self._to_collection(record)

    def update_collection(
        self,
        *,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
        embedding_model: str | None = None,
        chunk_template: str | None = None,
        system_prompt: str | None = None,
        top_k: int | None = None,
        vector_weight: float | None = None,
    ) -> Collection:
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Collection not found.")
        if name is not None:
            duplicate = self._session.scalar(
                select(CollectionRecord).where(
                    CollectionRecord.tenant_id == self._tenant_id,
                    func.lower(CollectionRecord.name) == name.lower(),
                    CollectionRecord.id != collection_id,
                )
            )
            if duplicate is not None:
                raise ValueError("A collection with that name already exists.")
            record.name = name
        if description is not None:
            record.description = description
        if embedding_model is not None:
            record.embedding_model = embedding_model
        if chunk_template is not None:
            record.chunk_template = chunk_template
        if system_prompt is not None:
            record.system_prompt = system_prompt
        if top_k is not None:
            record.top_k = top_k
        if vector_weight is not None:
            record.vector_weight = vector_weight
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_collection(record)

    def delete_collection(self, *, collection_id: str) -> None:
        record = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Collection not found.")
        self._session.execute(
            delete(GraphTripleRecord).where(
                GraphTripleRecord.collection_id == collection_id,
                GraphTripleRecord.tenant_id == self._tenant_id,
            )
        )
        document_ids = list(
            self._session.scalars(
                select(DocumentRecord.id).where(
                    DocumentRecord.collection_id == collection_id,
                    DocumentRecord.tenant_id == self._tenant_id,
                )
            )
        )
        if document_ids:
            self._session.execute(delete(ChunkRecord).where(ChunkRecord.document_id.in_(document_ids)))
            self._session.execute(delete(DocumentRecord).where(DocumentRecord.id.in_(document_ids)))
        # Drop any per-collection memberships
        self._session.execute(
            delete(CollectionMembershipRecord).where(
                CollectionMembershipRecord.collection_id == collection_id,
                CollectionMembershipRecord.tenant_id == self._tenant_id,
            )
        )
        self._session.delete(record)
        self._session.commit()

    # ---- per-collection RBAC --------------------------------------------------

    def list_collection_members(self, *, collection_id: str) -> list[CollectionMembership]:
        # Confirm collection exists in this tenant
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")
        statement = (
            select(CollectionMembershipRecord)
            .where(
                CollectionMembershipRecord.collection_id == collection_id,
                CollectionMembershipRecord.tenant_id == self._tenant_id,
            )
            .order_by(CollectionMembershipRecord.created_at.asc())
        )
        return [self._to_membership(r) for r in self._session.scalars(statement)]

    def upsert_collection_member(
        self,
        *,
        collection_id: str,
        user_id: str,
        role: str,
    ) -> CollectionMembership:
        if role not in ("OWNER", "EDITOR", "VIEWER"):
            raise ValueError(f"Invalid collection role: {role!r}")
        # Confirm collection exists in this tenant
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")
        record = self._session.scalar(
            select(CollectionMembershipRecord).where(
                CollectionMembershipRecord.collection_id == collection_id,
                CollectionMembershipRecord.user_id == user_id,
                CollectionMembershipRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            record = CollectionMembershipRecord(
                tenant_id=self._tenant_id,
                collection_id=collection_id,
                user_id=user_id,
                role=role,
            )
            self._session.add(record)
        else:
            record.role = role
            record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_membership(record)

    def remove_collection_member(self, *, collection_id: str, user_id: str) -> None:
        record = self._session.scalar(
            select(CollectionMembershipRecord).where(
                CollectionMembershipRecord.collection_id == collection_id,
                CollectionMembershipRecord.user_id == user_id,
                CollectionMembershipRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Membership not found.")
        self._session.delete(record)
        self._session.commit()

    def collection_member_role(
        self,
        *,
        collection_id: str,
        user_id: str,
    ) -> str | None:
        record = self._session.scalar(
            select(CollectionMembershipRecord).where(
                CollectionMembershipRecord.collection_id == collection_id,
                CollectionMembershipRecord.user_id == user_id,
                CollectionMembershipRecord.tenant_id == self._tenant_id,
            )
        )
        return record.role if record is not None else None

    def list_collection_ids_for_user(self, *, user_id: str) -> list[str]:
        statement = select(CollectionMembershipRecord.collection_id).where(
            CollectionMembershipRecord.user_id == user_id,
            CollectionMembershipRecord.tenant_id == self._tenant_id,
        )
        return list(self._session.scalars(statement))

    @staticmethod
    def _to_membership(record: CollectionMembershipRecord) -> CollectionMembership:
        return CollectionMembership(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            user_id=record.user_id,
            role=record.role,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def create_document(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
    ) -> Document:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        record = DocumentRecord(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="PENDING",
        )
        collection.document_count += 1
        collection.updated_at = utc_now()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def list_documents(self, collection_id: str) -> list[Document]:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        statement = (
            select(DocumentRecord)
            .where(
                DocumentRecord.collection_id == collection_id,
                DocumentRecord.tenant_id == self._tenant_id,
            )
            .order_by(DocumentRecord.created_at.asc())
        )
        return [self._to_document(record) for record in self._session.scalars(statement)]

    def get_document(self, document_id: str) -> Document:
        record = self._get_document_record(document_id)
        return self._to_document(record)

    def find_document_by_name(self, collection_id: str, name: str) -> Document | None:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.tenant_id == self._tenant_id,
                DocumentRecord.collection_id == collection_id,
                DocumentRecord.name == name,
            ).order_by(DocumentRecord.created_at.desc()).limit(1)
        )
        return self._to_document(record) if record is not None else None

    def update_document_storage(
        self,
        *,
        document_id: str,
        object_key: str,
        content_sha256: str,
        size_bytes: int,
    ) -> Document:
        """Overwrite storage metadata and reset status to PENDING for re-processing."""
        record = self._get_document_record(document_id)
        record.object_key = object_key
        record.content_sha256 = content_sha256
        record.size_bytes = size_bytes
        record.status = "PENDING"
        record.error_message = None
        record.parsed_text_key = None
        record.parsed_at = None
        record.page_count = None
        record.parser_name = None
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def create_document_with_storage(
        self,
        *,
        collection_id: str,
        name: str,
        mime_type: str,
        size_bytes: int,
        object_key: str,
        content_sha256: str,
    ) -> Document:
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")

        record = DocumentRecord(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="PENDING",
            object_key=object_key,
            content_sha256=content_sha256,
        )
        collection.document_count += 1
        collection.updated_at = utc_now()
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def update_status(
        self,
        *,
        document_id: str,
        status: str,
        error_message: str | None = None,
        parsed_text_key: str | None = None,
        page_count: int | None = None,
        parser_name: str | None = None,
    ) -> Document:
        record = self._get_document_record(document_id)
        record.status = status
        if status == "FAILED":
            record.error_message = error_message
        elif status in ("PARSED", "READY"):
            record.error_message = None
            if status == "PARSED":
                record.parsed_at = utc_now()
            if parsed_text_key is not None:
                record.parsed_text_key = parsed_text_key
            if page_count is not None:
                record.page_count = page_count
            if parser_name is not None:
                record.parser_name = parser_name
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def replace_chunks(
        self,
        *,
        document_id: str,
        chunks: list[dict],
        template_name: str,
    ) -> list[Chunk]:
        document = self._get_document_record(document_id)
        self._session.execute(delete(ChunkRecord).where(ChunkRecord.document_id == document_id))
        records: list[ChunkRecord] = []
        for ordinal, chunk in enumerate(chunks):
            text = chunk["text"]
            metadata = chunk.get("metadata") or {}
            record = ChunkRecord(
                tenant_id=self._tenant_id,
                collection_id=document.collection_id,
                document_id=document_id,
                ordinal=ordinal,
                text=text,
                char_count=len(text),
                token_count=max(1, len(text.split())),
                template_name=template_name,
                metadata_json=json.dumps(metadata, separators=(",", ":"), sort_keys=True),
                parent_chunk_id=chunk.get("parent_chunk_id"),
                is_indexable=int(chunk.get("is_indexable", True)),
            )
            self._session.add(record)
            records.append(record)
        self._session.commit()
        for record in records:
            self._session.refresh(record)
        return [self._to_chunk(r) for r in records]

    def get_chunk_by_id(self, chunk_id: str) -> Chunk:
        record = self._session.scalar(
            select(ChunkRecord).where(
                ChunkRecord.id == chunk_id,
                ChunkRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Chunk not found.")
        return self._to_chunk(record)

    def list_chunks(self, *, document_id: str) -> list[Chunk]:
        statement = (
            select(ChunkRecord)
            .where(
                ChunkRecord.document_id == document_id,
                ChunkRecord.tenant_id == self._tenant_id,
            )
            .order_by(ChunkRecord.ordinal.asc())
        )
        return [self._to_chunk(r) for r in self._session.scalars(statement)]

    def mark_chunks_indexed(self, *, document_id: str, indexed_at: datetime) -> None:
        records = self._session.scalars(
            select(ChunkRecord).where(
                ChunkRecord.document_id == document_id,
                ChunkRecord.tenant_id == self._tenant_id,
            )
        )
        for record in records:
            record.indexed_at = indexed_at
        self._session.commit()

    def _get_document_record(self, document_id: str) -> DocumentRecord:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == document_id,
                DocumentRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Document not found.")
        return record

    def delete_document(self, *, document_id: str) -> None:
        record = self._get_document_record(document_id)
        # Chunks are deleted via cascade in DB; if not, delete explicitly
        self._session.execute(delete(ChunkRecord).where(ChunkRecord.document_id == document_id))
        self._session.execute(
            delete(GraphTripleRecord).where(
                GraphTripleRecord.document_id == document_id,
                GraphTripleRecord.tenant_id == self._tenant_id,
            )
        )
        # Update collection document count
        collection = self._session.scalar(
            select(CollectionRecord).where(CollectionRecord.id == record.collection_id)
        )
        if collection and collection.document_count > 0:
            collection.document_count -= 1
        self._session.delete(record)
        self._session.commit()

    def replace_graph_triples(self, *, document_id: str, triples: list[dict]) -> list[GraphTriple]:
        document = self._get_document_record(document_id)
        self._session.execute(
            delete(GraphTripleRecord).where(
                GraphTripleRecord.document_id == document_id,
                GraphTripleRecord.tenant_id == self._tenant_id,
            )
        )
        records: list[GraphTripleRecord] = []
        for triple in triples:
            subject = str(triple.get("subject") or "").strip()
            predicate = str(triple.get("predicate") or "").strip()
            object_value = str(triple.get("object") or triple.get("object_") or "").strip()
            if not subject or not predicate or not object_value:
                continue
            try:
                confidence = float(triple.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0
            record = GraphTripleRecord(
                tenant_id=self._tenant_id,
                collection_id=document.collection_id,
                document_id=document_id,
                subject=subject[:1000],
                predicate=predicate[:1000],
                object_=object_value[:1000],
                confidence=max(0.0, min(1.0, confidence)),
            )
            self._session.add(record)
            records.append(record)
        self._session.commit()
        for record in records:
            self._session.refresh(record)
        return [self._to_graph_triple(record) for record in records]

    def list_graph_triples(
        self,
        *,
        collection_id: str | None = None,
        document_id: str | None = None,
        entity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GraphTriple]:
        statement = select(GraphTripleRecord).where(GraphTripleRecord.tenant_id == self._tenant_id)
        if collection_id is not None:
            statement = statement.where(GraphTripleRecord.collection_id == collection_id)
        if document_id is not None:
            statement = statement.where(GraphTripleRecord.document_id == document_id)
        if entity:
            pattern = f"%{entity.lower()}%"
            statement = statement.where(
                or_(
                    func.lower(GraphTripleRecord.subject).like(pattern),
                    func.lower(GraphTripleRecord.object_).like(pattern),
                )
            )
        statement = statement.order_by(GraphTripleRecord.created_at.desc()).offset(max(0, offset)).limit(limit)
        return [self._to_graph_triple(record) for record in self._session.scalars(statement)]

    def count_collections(self) -> int:
        statement = select(func.count(CollectionRecord.id)).where(CollectionRecord.tenant_id == self._tenant_id)
        return int(self._session.scalar(statement) or 0)

    def count_documents(self) -> int:
        statement = select(func.count(DocumentRecord.id)).where(DocumentRecord.tenant_id == self._tenant_id)
        return int(self._session.scalar(statement) or 0)

    @staticmethod
    def _to_collection(record: CollectionRecord) -> Collection:
        return Collection(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            description=record.description,
            embedding_model=record.embedding_model,
            chunk_template=record.chunk_template,
            system_prompt=record.system_prompt,
            top_k=record.top_k,
            vector_weight=record.vector_weight,
            created_at=record.created_at,
            updated_at=record.updated_at,
            document_count=record.document_count,
        )

    @staticmethod
    def _to_graph_triple(record: GraphTripleRecord) -> GraphTriple:
        return GraphTriple(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            document_id=record.document_id,
            subject=record.subject,
            predicate=record.predicate,
            object=record.object_,
            confidence=record.confidence,
            created_at=record.created_at,
        )

    @staticmethod
    def _to_chunk(record: ChunkRecord) -> Chunk:
        try:
            metadata = json.loads(record.metadata_json) if record.metadata_json else {}
        except json.JSONDecodeError:
            metadata = {}
        return Chunk(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            document_id=record.document_id,
            ordinal=record.ordinal,
            text=record.text,
            char_count=record.char_count,
            token_count=record.token_count,
            template_name=record.template_name,
            metadata=metadata,
            parent_chunk_id=record.parent_chunk_id,
            is_indexable=bool(record.is_indexable),
            indexed_at=record.indexed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def set_document_tags(self, *, document_id: str, tags: list[str]) -> Document:
        record = self._get_document_record(document_id)
        normalized = sorted({tag.strip() for tag in tags if tag and tag.strip()})
        record.tags_json = json.dumps(normalized)
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_document(record)

    def list_documents_by_tag(self, *, collection_id: str | None, tag: str) -> list[Document]:
        statement = select(DocumentRecord).where(
            DocumentRecord.tenant_id == self._tenant_id,
            DocumentRecord.tags_json.like(f'%"{tag}"%'),
        )
        if collection_id:
            statement = statement.where(DocumentRecord.collection_id == collection_id)
        return [self._to_document(r) for r in self._session.scalars(statement)]

    @staticmethod
    def _to_document(record: DocumentRecord) -> Document:
        try:
            tags = json.loads(record.tags_json) if record.tags_json else []
        except json.JSONDecodeError:
            tags = []
        return Document(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            name=record.name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            status=record.status,
            object_key=record.object_key,
            parsed_text_key=record.parsed_text_key,
            content_sha256=record.content_sha256,
            page_count=record.page_count,
            parser_name=record.parser_name,
            error_message=record.error_message,
            parsed_at=record.parsed_at,
            tags=tags if isinstance(tags, list) else [],
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class SqlAlchemyAgentStore(AgentStorePort):
    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def list_agents(self) -> list[Agent]:
        statement = (
            select(AgentRecord)
            .where(AgentRecord.tenant_id == self._tenant_id)
            .order_by(AgentRecord.created_at.desc())
        )
        return [self._to_agent(record) for record in self._session.scalars(statement)]

    def create_agent(
        self,
        *,
        name: str,
        description: str | None,
        definition: dict,
        template_id: str | None = None,
    ) -> Agent:
        duplicate = self._session.scalar(
            select(AgentRecord).where(
                AgentRecord.tenant_id == self._tenant_id,
                func.lower(AgentRecord.name) == name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("An agent with that name already exists.")
        record = AgentRecord(
            tenant_id=self._tenant_id,
            name=name.strip(),
            description=description,
            definition_json=json.dumps(definition),
            published=0,
            template_id=template_id,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_agent(record)

    def get_agent(self, agent_id: str) -> Agent:
        return self._to_agent(self._get_agent_record(agent_id))

    def update_agent(
        self,
        *,
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
        definition: dict | None = None,
        published: bool | None = None,
    ) -> Agent:
        record = self._get_agent_record(agent_id)
        if name is not None:
            duplicate = self._session.scalar(
                select(AgentRecord).where(
                    AgentRecord.tenant_id == self._tenant_id,
                    func.lower(AgentRecord.name) == name.lower(),
                    AgentRecord.id != agent_id,
                )
            )
            if duplicate is not None:
                raise ValueError("An agent with that name already exists.")
            record.name = name.strip()
        if description is not None:
            record.description = description
        if definition is not None:
            record.definition_json = json.dumps(definition)
        if published is not None:
            record.published = int(bool(published))
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_agent(record)

    def delete_agent(self, agent_id: str) -> None:
        record = self._get_agent_record(agent_id)
        self._session.execute(
            delete(AgentRunRecord).where(
                AgentRunRecord.tenant_id == self._tenant_id,
                AgentRunRecord.agent_id == agent_id,
            )
        )
        self._session.delete(record)
        self._session.commit()

    def list_runs(self, agent_id: str) -> list[AgentRun]:
        self._get_agent_record(agent_id)
        statement = (
            select(AgentRunRecord)
            .where(
                AgentRunRecord.tenant_id == self._tenant_id,
                AgentRunRecord.agent_id == agent_id,
            )
            .order_by(AgentRunRecord.created_at.desc())
        )
        return [self._to_run(record) for record in self._session.scalars(statement)]

    def get_run(self, agent_id: str, run_id: str) -> AgentRun:
        return self._to_run(self._get_run_record(agent_id, run_id))

    def create_run(
        self,
        *,
        agent_id: str,
        input_payload: dict,
        replay_of_run_id: str | None = None,
        replay_from_event: int | None = None,
    ) -> AgentRun:
        self._get_agent_record(agent_id)
        record = AgentRunRecord(
            tenant_id=self._tenant_id,
            agent_id=agent_id,
            status="QUEUED",
            input_json=json.dumps(input_payload),
            output_json="{}",
            events_json="[]",
            replay_of_run_id=replay_of_run_id,
            replay_from_event=replay_from_event,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_run(record)

    def update_run(
        self,
        *,
        run_id: str,
        status: str,
        output: dict,
        events: list[dict],
        error_message: str | None = None,
        paused_at_node: str | None = None,
        cost_usd: float = 0.0,
        started: bool = False,
        completed: bool = False,
    ) -> AgentRun:
        record = self._session.scalar(
            select(AgentRunRecord).where(
                AgentRunRecord.id == run_id,
                AgentRunRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Agent run not found.")
        record.status = status
        record.output_json = json.dumps(output)
        record.events_json = json.dumps(events)
        record.error_message = error_message
        if paused_at_node is not None:
            record.paused_at_node = paused_at_node
        record.cost_usd = cost_usd
        if started and record.started_at is None:
            record.started_at = utc_now()
        if completed:
            record.completed_at = utc_now()
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_run(record)

    def _get_agent_record(self, agent_id: str) -> AgentRecord:
        record = self._session.scalar(
            select(AgentRecord).where(
                AgentRecord.id == agent_id,
                AgentRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Agent not found.")
        return record

    def _get_run_record(self, agent_id: str, run_id: str) -> AgentRunRecord:
        record = self._session.scalar(
            select(AgentRunRecord).where(
                AgentRunRecord.id == run_id,
                AgentRunRecord.agent_id == agent_id,
                AgentRunRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Agent run not found.")
        return record

    @staticmethod
    def _to_agent(record: AgentRecord) -> Agent:
        return Agent(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            description=record.description,
            definition=json.loads(record.definition_json or "{}"),
            published=bool(record.published),
            template_id=getattr(record, "template_id", None),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_run(record: AgentRunRecord) -> AgentRun:
        return AgentRun(
            id=record.id,
            tenant_id=record.tenant_id,
            agent_id=record.agent_id,
            status=record.status,
            input=json.loads(record.input_json or "{}"),
            output=json.loads(record.output_json or "{}"),
            events=json.loads(record.events_json or "[]"),
            error_message=record.error_message,
            paused_at_node=getattr(record, "paused_at_node", None),
            resumed_with=json.loads(getattr(record, "resumed_with_json", None) or "{}"),
            replay_of_run_id=getattr(record, "replay_of_run_id", None),
            replay_from_event=getattr(record, "replay_from_event", None),
            cost_usd=float(getattr(record, "cost_usd", 0.0) or 0.0),
            started_at=record.started_at,
            completed_at=record.completed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class SqlAlchemyConnectorStore(ConnectorStorePort):
    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def list_connectors(self, *, collection_id: str | None = None) -> list[Connector]:
        statement = select(ConnectorRecord).where(ConnectorRecord.tenant_id == self._tenant_id)
        if collection_id:
            statement = statement.where(ConnectorRecord.collection_id == collection_id)
        statement = statement.order_by(ConnectorRecord.created_at.desc())
        return [self._to_connector(r) for r in self._session.scalars(statement)]

    def create_connector(
        self,
        *,
        collection_id: str,
        name: str,
        kind: str,
        config: dict,
        sync_interval_seconds: int = 300,
    ) -> Connector:
        # Verify collection exists in this tenant
        collection = self._session.scalar(
            select(CollectionRecord).where(
                CollectionRecord.id == collection_id,
                CollectionRecord.tenant_id == self._tenant_id,
            )
        )
        if collection is None:
            raise KeyError("Collection not found.")
        duplicate = self._session.scalar(
            select(ConnectorRecord).where(
                ConnectorRecord.tenant_id == self._tenant_id,
                func.lower(ConnectorRecord.name) == name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("A connector with that name already exists.")
        record = ConnectorRecord(
            tenant_id=self._tenant_id,
            collection_id=collection_id,
            name=name.strip(),
            kind=kind,
            config_json=json.dumps(config or {}),
            enabled=1,
            sync_interval_seconds=max(30, sync_interval_seconds),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_connector(record)

    def get_connector(self, connector_id: str) -> Connector:
        return self._to_connector(self._get_record(connector_id))

    def update_connector(
        self,
        *,
        connector_id: str,
        name: str | None = None,
        config: dict | None = None,
        enabled: bool | None = None,
        sync_interval_seconds: int | None = None,
    ) -> Connector:
        record = self._get_record(connector_id)
        if name is not None:
            duplicate = self._session.scalar(
                select(ConnectorRecord).where(
                    ConnectorRecord.tenant_id == self._tenant_id,
                    func.lower(ConnectorRecord.name) == name.lower(),
                    ConnectorRecord.id != connector_id,
                )
            )
            if duplicate is not None:
                raise ValueError("A connector with that name already exists.")
            record.name = name.strip()
        if config is not None:
            record.config_json = json.dumps(config)
        if enabled is not None:
            record.enabled = 1 if enabled else 0
        if sync_interval_seconds is not None:
            record.sync_interval_seconds = max(30, sync_interval_seconds)
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_connector(record)

    def delete_connector(self, connector_id: str) -> None:
        record = self._get_record(connector_id)
        self._session.delete(record)
        self._session.commit()

    def record_sync(
        self,
        *,
        connector_id: str,
        last_sync_at: datetime,
        last_error: str | None,
        last_synced_count: int,
        seen_hashes: list[str],
    ) -> Connector:
        record = self._get_record(connector_id)
        record.last_sync_at = last_sync_at
        record.last_error = last_error
        record.last_synced_count = last_synced_count
        # Cap stored hashes so the row doesn't grow unbounded
        capped = list(seen_hashes)[-5000:]
        record.seen_hashes_json = json.dumps(capped)
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_connector(record)

    def list_enabled_connectors_across_tenants(self) -> list[tuple[str, Connector]]:
        statement = select(ConnectorRecord).where(ConnectorRecord.enabled == 1)
        return [(r.tenant_id, self._to_connector(r)) for r in self._session.scalars(statement)]

    def _get_record(self, connector_id: str) -> ConnectorRecord:
        record = self._session.scalar(
            select(ConnectorRecord).where(
                ConnectorRecord.id == connector_id,
                ConnectorRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Connector not found.")
        return record

    @staticmethod
    def _to_connector(record: ConnectorRecord) -> Connector:
        try:
            config = json.loads(record.config_json) if record.config_json else {}
        except json.JSONDecodeError:
            config = {}
        try:
            seen = json.loads(record.seen_hashes_json) if record.seen_hashes_json else []
        except json.JSONDecodeError:
            seen = []
        return Connector(
            id=record.id,
            tenant_id=record.tenant_id,
            collection_id=record.collection_id,
            name=record.name,
            kind=record.kind,
            config=config if isinstance(config, dict) else {},
            enabled=bool(record.enabled),
            sync_interval_seconds=record.sync_interval_seconds,
            last_sync_at=record.last_sync_at,
            last_error=record.last_error,
            last_synced_count=record.last_synced_count,
            seen_hashes=seen if isinstance(seen, list) else [],
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class SqlAlchemyDeploymentStore(DeploymentStorePort):
    """Per-tenant CRUD for in-app Deploy Manager rows.

    The cross-tenant `get_deployment_by_slug` is intentionally untenanted —
    it's used by the public surface where the slug IS the entire address.
    """

    def __init__(self, session: Session, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def list_deployments(self) -> list[Deployment]:
        statement = (
            select(DeploymentRecord)
            .where(
                DeploymentRecord.tenant_id == self._tenant_id,
                DeploymentRecord.status != "DELETED",
            )
            .order_by(DeploymentRecord.created_at.desc())
        )
        return [self._to_deployment(r) for r in self._session.scalars(statement)]

    def create_deployment(
        self,
        *,
        name: str,
        slug: str,
        kind: str,
        target_kind: str,
        target_id: str,
        system_prompt_override: str | None,
        model_provider: str | None,
        model_name: str | None,
        anonymous_allowed: bool,
        rate_limit_per_minute: int,
        daily_message_quota: int,
        branding: dict,
        definition_snapshot: dict,
    ) -> Deployment:
        # Slug is globally unique
        existing_slug = self._session.scalar(
            select(DeploymentRecord).where(DeploymentRecord.slug == slug)
        )
        if existing_slug is not None:
            raise ValueError("Slug is already taken.")
        # Name is unique within the tenant
        duplicate_name = self._session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.tenant_id == self._tenant_id,
                func.lower(DeploymentRecord.name) == name.lower(),
                DeploymentRecord.status != "DELETED",
            )
        )
        if duplicate_name is not None:
            raise ValueError("A deployment with that name already exists.")
        record = DeploymentRecord(
            tenant_id=self._tenant_id,
            name=name.strip(),
            slug=slug,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            system_prompt_override=system_prompt_override,
            model_provider=model_provider,
            model_name=model_name,
            anonymous_allowed=1 if anonymous_allowed else 0,
            rate_limit_per_minute=max(1, rate_limit_per_minute),
            daily_message_quota=max(0, daily_message_quota),
            branding_json=json.dumps(branding or {}),
            definition_snapshot_json=json.dumps(definition_snapshot or {}),
            status="ACTIVE",
            version=1,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_deployment(record)

    def get_deployment(self, deployment_id: str) -> Deployment:
        return self._to_deployment(self._get_record(deployment_id))

    def get_deployment_by_slug(self, slug: str) -> tuple[str, Deployment] | None:
        record = self._session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.slug == slug,
                DeploymentRecord.status == "ACTIVE",
            )
        )
        if record is None:
            return None
        return record.tenant_id, self._to_deployment(record)

    def update_deployment(
        self,
        *,
        deployment_id: str,
        name: str | None = None,
        system_prompt_override: str | None = None,
        anonymous_allowed: bool | None = None,
        rate_limit_per_minute: int | None = None,
        daily_message_quota: int | None = None,
        branding: dict | None = None,
        status: str | None = None,
    ) -> Deployment:
        record = self._get_record(deployment_id)
        if name is not None:
            duplicate = self._session.scalar(
                select(DeploymentRecord).where(
                    DeploymentRecord.tenant_id == self._tenant_id,
                    func.lower(DeploymentRecord.name) == name.lower(),
                    DeploymentRecord.id != deployment_id,
                    DeploymentRecord.status != "DELETED",
                )
            )
            if duplicate is not None:
                raise ValueError("A deployment with that name already exists.")
            record.name = name.strip()
        if system_prompt_override is not None:
            record.system_prompt_override = system_prompt_override
            record.version += 1
        if anonymous_allowed is not None:
            record.anonymous_allowed = 1 if anonymous_allowed else 0
        if rate_limit_per_minute is not None:
            record.rate_limit_per_minute = max(1, rate_limit_per_minute)
        if daily_message_quota is not None:
            record.daily_message_quota = max(0, daily_message_quota)
        if branding is not None:
            record.branding_json = json.dumps(branding)
        if status is not None:
            if status not in ("ACTIVE", "PAUSED", "DELETED"):
                raise ValueError(f"Invalid deployment status: {status!r}")
            record.status = status
        record.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(record)
        return self._to_deployment(record)

    def delete_deployment(self, deployment_id: str) -> None:
        record = self._get_record(deployment_id)
        # Soft-delete: keep the row for audit, free the slug only on hard-delete
        record.status = "DELETED"
        record.updated_at = utc_now()
        self._session.commit()

    def increment_message_counters(self, deployment_id: str) -> Deployment:
        record = self._get_record(deployment_id)
        now = utc_now()
        # Reset the today-counter if we crossed midnight UTC
        if record.today_window_start is None or record.today_window_start.date() != now.date():
            record.today_window_start = now
            record.today_message_count = 0
        record.today_message_count += 1
        record.message_count += 1
        record.last_message_at = now
        record.updated_at = now
        self._session.commit()
        self._session.refresh(record)
        return self._to_deployment(record)

    def _get_record(self, deployment_id: str) -> DeploymentRecord:
        record = self._session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.id == deployment_id,
                DeploymentRecord.tenant_id == self._tenant_id,
            )
        )
        if record is None:
            raise KeyError("Deployment not found.")
        return record

    @staticmethod
    def _to_deployment(record: DeploymentRecord) -> Deployment:
        try:
            branding = json.loads(record.branding_json or "{}")
        except json.JSONDecodeError:
            branding = {}
        try:
            snapshot = json.loads(record.definition_snapshot_json or "{}")
        except json.JSONDecodeError:
            snapshot = {}
        return Deployment(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            slug=record.slug,
            kind=record.kind,
            target_kind=record.target_kind,
            target_id=record.target_id,
            system_prompt_override=record.system_prompt_override,
            model_provider=record.model_provider,
            model_name=record.model_name,
            anonymous_allowed=bool(record.anonymous_allowed),
            rate_limit_per_minute=record.rate_limit_per_minute,
            daily_message_quota=record.daily_message_quota,
            branding=branding if isinstance(branding, dict) else {},
            definition_snapshot=snapshot if isinstance(snapshot, dict) else {},
            status=record.status,
            version=record.version,
            message_count=record.message_count,
            today_message_count=record.today_message_count,
            today_window_start=record.today_window_start,
            last_message_at=record.last_message_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class DeploymentBySlugLookup:
    """Cross-tenant slug lookup helper for the public chat surface.

    A separate class because it deliberately does NOT bind to a tenant_id —
    public consumers don't have one. Internal CRUD goes through
    SqlAlchemyDeploymentStore which IS tenant-scoped.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, slug: str) -> tuple[str, Deployment] | None:
        record = self._session.scalar(
            select(DeploymentRecord).where(
                DeploymentRecord.slug == slug,
                DeploymentRecord.status == "ACTIVE",
            )
        )
        if record is None:
            return None
        return record.tenant_id, SqlAlchemyDeploymentStore._to_deployment(record)

    def increment_counters(self, deployment_id: str) -> Deployment:
        record = self._session.scalar(
            select(DeploymentRecord).where(DeploymentRecord.id == deployment_id)
        )
        if record is None:
            raise KeyError("Deployment not found.")
        now = utc_now()
        if record.today_window_start is None or record.today_window_start.date() != now.date():
            record.today_window_start = now
            record.today_message_count = 0
        record.today_message_count += 1
        record.message_count += 1
        record.last_message_at = now
        record.updated_at = now
        self._session.commit()
        self._session.refresh(record)
        return SqlAlchemyDeploymentStore._to_deployment(record)
