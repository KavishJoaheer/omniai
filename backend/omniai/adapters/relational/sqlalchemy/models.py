from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from omniai.domain.knowledge.models import utc_now


def generate_prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class TenantRecord(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("ten"))
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    collections: Mapped[list["CollectionRecord"]] = relationship(back_populates="tenant")
    documents: Mapped[list["DocumentRecord"]] = relationship(back_populates="tenant")
    users: Mapped[list["UserRecord"]] = relationship(back_populates="primary_tenant")
    memberships: Mapped[list["TenantMembershipRecord"]] = relationship(back_populates="tenant")
    teams: Mapped[list["TeamRecord"]] = relationship(back_populates="tenant")
    api_keys: Mapped[list["ApiKeyRecord"]] = relationship(back_populates="tenant")
    audit_events: Mapped[list["AuditEventRecord"]] = relationship(back_populates="tenant")
    providers: Mapped[list["ProviderRecord"]] = relationship(back_populates="tenant")
    graph_triples: Mapped[list["GraphTripleRecord"]] = relationship(back_populates="tenant")
    agents: Mapped[list["AgentRecord"]] = relationship(back_populates="tenant")
    agent_runs: Mapped[list["AgentRunRecord"]] = relationship(back_populates="tenant")


class CollectionRecord(TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_collection_tenant_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("col"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), default="text-embedding-default")
    chunk_template: Mapped[str] = mapped_column(String(64), default="general")
    system_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    top_k: Mapped[int] = mapped_column(Integer, default=8)
    vector_weight: Mapped[float] = mapped_column(Float, default=0.6)
    document_count: Mapped[int] = mapped_column(Integer, default=0)

    tenant: Mapped[TenantRecord] = relationship(back_populates="collections")
    documents: Mapped[list["DocumentRecord"]] = relationship(back_populates="collection")


class DocumentRecord(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("doc"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parsed_text_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    parser_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text(), default="[]")

    tenant: Mapped[TenantRecord] = relationship(back_populates="documents")
    collection: Mapped[CollectionRecord] = relationship(back_populates="documents")


class UserRecord(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("usr"))
    primary_tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    # Password-reset flow
    reset_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    primary_tenant: Mapped[TenantRecord] = relationship(back_populates="users")
    tenant_memberships: Mapped[list["TenantMembershipRecord"]] = relationship(back_populates="user")
    team_memberships: Mapped[list["TeamMembershipRecord"]] = relationship(back_populates="user")
    created_api_keys: Mapped[list["ApiKeyRecord"]] = relationship(back_populates="created_by_user")
    audit_events: Mapped[list["AuditEventRecord"]] = relationship(back_populates="actor_user")


class RevokedTokenRecord(Base):
    """Blocklist for session tokens that have been explicitly logged out.

    Each row stores the ``jti`` (JWT-style token-ID), the user who owned it,
    and the token's natural expiry time so a background cleanup job can prune
    rows that would have expired anyway.
    """
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TenantMembershipRecord(TimestampMixin, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("tmem"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="MEMBER")

    tenant: Mapped[TenantRecord] = relationship(back_populates="memberships")
    user: Mapped[UserRecord] = relationship(back_populates="tenant_memberships")


class TeamRecord(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_team_tenant_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("team"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    tenant: Mapped[TenantRecord] = relationship(back_populates="teams")
    memberships: Mapped[list["TeamMembershipRecord"]] = relationship(back_populates="team")


class TeamMembershipRecord(TimestampMixin, Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_membership"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("tmm"))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="MEMBER")

    team: Mapped[TeamRecord] = relationship(back_populates="memberships")
    user: Mapped[UserRecord] = relationship(back_populates="team_memberships")


class ApiKeyRecord(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("key"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[str] = mapped_column(Text(), default="")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[TenantRecord] = relationship(back_populates="api_keys")
    created_by_user: Mapped[UserRecord] = relationship(back_populates="created_api_keys")


class ChunkRecord(TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("chk"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text())
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    template_name: Mapped[str] = mapped_column(String(64), default="general")
    metadata_json: Mapped[str] = mapped_column(Text(), default="{}")
    parent_chunk_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_indexable: Mapped[int] = mapped_column(Integer, default=1)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeploymentRecord(TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_deployment_slug"),
        UniqueConstraint("tenant_id", "name", name="uq_deployment_tenant_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("dep"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(32))
    system_prompt_override: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    anonymous_allowed: Mapped[int] = mapped_column(Integer, default=1)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    daily_message_quota: Mapped[int] = mapped_column(Integer, default=500)
    branding_json: Mapped[str] = mapped_column(Text(), default="{}")
    definition_snapshot_json: Mapped[str] = mapped_column(Text(), default="{}")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    today_message_count: Mapped[int] = mapped_column(Integer, default=0)
    today_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CollectionMembershipRecord(TimestampMixin, Base):
    __tablename__ = "collection_memberships"
    __table_args__ = (UniqueConstraint("collection_id", "user_id", name="uq_collection_membership"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("cmem"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="VIEWER")


class ConnectorRecord(TimestampMixin, Base):
    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connector_tenant_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("cnt"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32), index=True)
    config_json: Mapped[str] = mapped_column(Text(), default="{}")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_synced_count: Mapped[int] = mapped_column(Integer, default=0)
    seen_hashes_json: Mapped[str] = mapped_column(Text(), default="[]")


class ProviderRecord(TimestampMixin, Base):
    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "name", name="uq_provider_tenant_kind_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("prv"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=0)
    has_credentials: Mapped[int] = mapped_column(Integer, default=0)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text(), nullable=True)
    options_json: Mapped[str] = mapped_column(Text(), default="{}")

    tenant: Mapped[TenantRecord] = relationship(back_populates="providers")


class GraphTripleRecord(Base):
    __tablename__ = "graph_triples"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("gtr"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    subject: Mapped[str] = mapped_column(Text())
    predicate: Mapped[str] = mapped_column(Text())
    object_: Mapped[str] = mapped_column("object", Text())
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[TenantRecord] = relationship(back_populates="graph_triples")


class ConversationRecord(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("cnv"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    system_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    collection_ids_json: Mapped[str] = mapped_column(Text(), default="[]")
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[str] = mapped_column(String(16), default="0.2")
    top_k: Mapped[int] = mapped_column(Integer, default=8)
    vector_weight: Mapped[str] = mapped_column(String(16), default="0.6")
    pinned: Mapped[int] = mapped_column(Integer, default=0)


class AgentRecord(TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_agent_tenant_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("agt"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    definition_json: Mapped[str] = mapped_column(Text(), default="{}")
    published: Mapped[int] = mapped_column(Integer, default=0)

    tenant: Mapped[TenantRecord] = relationship(back_populates="agents")
    runs: Mapped[list["AgentRunRecord"]] = relationship(back_populates="agent")


class AgentRunRecord(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("run"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    input_json: Mapped[str] = mapped_column(Text(), default="{}")
    output_json: Mapped[str] = mapped_column(Text(), default="{}")
    events_json: Mapped[str] = mapped_column(Text(), default="[]")
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[TenantRecord] = relationship(back_populates="agent_runs")
    agent: Mapped[AgentRecord] = relationship(back_populates="runs")


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("msg"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text(), default="")
    citations_json: Mapped[str] = mapped_column(Text(), default="[]")
    usage_json: Mapped[str] = mapped_column(Text(), default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("aud"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    detail_json: Mapped[str] = mapped_column(Text(), default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[TenantRecord] = relationship(back_populates="audit_events")
    actor_user: Mapped[UserRecord | None] = relationship(back_populates="audit_events")
