from __future__ import annotations

from pydantic import BaseModel, Field

from omniai.application.store import KnowledgeStore
from omniai.domain.knowledge.models import Collection, CollectionMembership, Document


# Tenant-level roles whose holders bypass per-collection membership checks.
_TENANT_BYPASS_ROLES = frozenset({"OWNER", "ADMIN"})


def role_grants_collection_access(*, tenant_role: str, required: str) -> bool:
    """True iff a tenant-level OWNER/ADMIN automatically gets the requested
    `required` access level on any collection in their tenant."""
    return tenant_role in _TENANT_BYPASS_ROLES


def collection_role_meets(member_role: str | None, *, required: str) -> bool:
    """Check whether a per-collection role is at least `required`."""
    rank = {"VIEWER": 1, "EDITOR": 2, "OWNER": 3}
    if member_role is None:
        return False
    return rank.get(member_role, 0) >= rank.get(required, 99)


class CreateCollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    embedding_model: str = "text-embedding-default"
    chunk_template: str = "general"
    system_prompt: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    vector_weight: float = Field(default=0.6, ge=0.0, le=1.0)


class UpdateCollectionInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    embedding_model: str | None = None
    chunk_template: str | None = None
    system_prompt: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)


class CreateDocumentInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    mime_type: str = "application/octet-stream"
    size_bytes: int = Field(default=0, ge=0)


class KnowledgeService:
    """Knowledge-base service.

    When constructed with `tenant_role` + `user_id`, list/get operations
    enforce per-collection membership: OWNER/ADMIN tenant roles see every
    collection in the tenant; everyone else only sees collections they have
    a CollectionMembership row for.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        tenant_role: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self._store = store
        self._tenant_role = tenant_role or "OWNER"
        self._user_id = user_id

    # ---- access predicates ---------------------------------------------------

    def _bypass(self) -> bool:
        return role_grants_collection_access(tenant_role=self._tenant_role, required="VIEWER")

    def _can_access(self, collection_id: str, *, required: str) -> bool:
        if self._bypass():
            return True
        if self._user_id is None:
            return False
        member_role = self._store.collection_member_role(
            collection_id=collection_id, user_id=self._user_id
        )
        return collection_role_meets(member_role, required=required)

    def assert_collection_access(self, collection_id: str, *, required: str = "VIEWER") -> None:
        """Raises KeyError if the principal cannot access the collection at the
        required level. KeyError (not PermissionError) so the existing 404
        error mapping in the routes works without leaking existence info."""
        if not self._can_access(collection_id, required=required):
            raise KeyError("Collection not found.")

    # ---- collection CRUD with membership filtering ---------------------------

    def list_collections(self) -> list[Collection]:
        all_collections = self._store.list_collections()
        if self._bypass():
            return all_collections
        if self._user_id is None:
            return []
        visible = set(self._store.list_collection_ids_for_user(user_id=self._user_id))
        return [c for c in all_collections if c.id in visible]

    def create_collection(self, payload: CreateCollectionInput) -> Collection:
        collection = self._store.create_collection(
            name=payload.name,
            description=payload.description,
            embedding_model=payload.embedding_model,
            chunk_template=payload.chunk_template,
            system_prompt=payload.system_prompt,
            top_k=payload.top_k,
            vector_weight=payload.vector_weight,
        )
        # Whoever creates the collection is implicitly its OWNER. This makes
        # personal/non-admin users still able to see what they made.
        if self._user_id is not None and not self._bypass():
            self._store.upsert_collection_member(
                collection_id=collection.id, user_id=self._user_id, role="OWNER"
            )
        return collection

    def get_collection(self, collection_id: str) -> Collection:
        self.assert_collection_access(collection_id, required="VIEWER")
        return self._store.get_collection(collection_id)

    def update_collection(self, collection_id: str, payload: UpdateCollectionInput) -> Collection:
        self.assert_collection_access(collection_id, required="EDITOR")
        fields = payload.model_fields_set
        return self._store.update_collection(
            collection_id=collection_id,
            name=payload.name if "name" in fields else None,
            description=payload.description if "description" in fields else None,
            embedding_model=payload.embedding_model if "embedding_model" in fields else None,
            chunk_template=payload.chunk_template if "chunk_template" in fields else None,
            system_prompt=payload.system_prompt if "system_prompt" in fields else None,
            top_k=payload.top_k if "top_k" in fields else None,
            vector_weight=payload.vector_weight if "vector_weight" in fields else None,
        )

    def list_graph_triples(
        self,
        *,
        collection_id: str | None = None,
        document_id: str | None = None,
        entity: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        return self._store.list_graph_triples(
            collection_id=collection_id,
            document_id=document_id,
            entity=entity,
            limit=limit,
            offset=offset,
        )

    def list_documents(self, collection_id: str) -> list[Document]:
        self.assert_collection_access(collection_id, required="VIEWER")
        return self._store.list_documents(collection_id)

    def get_document(self, document_id: str) -> Document:
        document = self._store.get_document(document_id)
        self.assert_collection_access(document.collection_id, required="VIEWER")
        return document

    def update_document_status(self, document_id: str, status: str) -> Document:
        document = self._store.get_document(document_id)
        self.assert_collection_access(document.collection_id, required="EDITOR")
        return self._store.update_status(document_id=document_id, status=status)

    def create_document(self, collection_id: str, payload: CreateDocumentInput) -> Document:
        self.assert_collection_access(collection_id, required="EDITOR")
        return self._store.create_document(
            collection_id=collection_id,
            name=payload.name,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
        )

    def set_document_tags(self, *, document_id: str, tags: list[str]) -> Document:
        return self._store.set_document_tags(document_id=document_id, tags=tags)

    def list_documents_by_tag(self, *, collection_id: str | None, tag: str) -> list[Document]:
        return self._store.list_documents_by_tag(collection_id=collection_id, tag=tag)

    def count_collections(self) -> int:
        return self._store.count_collections()

    def count_documents(self) -> int:
        return self._store.count_documents()

    # ---- per-collection membership management --------------------------------
    # Membership writes require OWNER on the collection (or tenant OWNER/ADMIN).

    def list_collection_members(self, collection_id: str) -> list[CollectionMembership]:
        self.assert_collection_access(collection_id, required="VIEWER")
        return self._store.list_collection_members(collection_id=collection_id)

    def upsert_collection_member(
        self, *, collection_id: str, user_id: str, role: str
    ) -> CollectionMembership:
        self.assert_collection_access(collection_id, required="OWNER")
        return self._store.upsert_collection_member(
            collection_id=collection_id, user_id=user_id, role=role
        )

    def remove_collection_member(self, *, collection_id: str, user_id: str) -> None:
        self.assert_collection_access(collection_id, required="OWNER")
        self._store.remove_collection_member(collection_id=collection_id, user_id=user_id)
