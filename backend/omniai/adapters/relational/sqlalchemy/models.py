from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class CollectionRecord(TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_collection_tenant_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: generate_prefixed_id("col"))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), default="text-embedding-default")
    chunk_template: Mapped[str] = mapped_column(String(64), default="general")
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

    primary_tenant: Mapped[TenantRecord] = relationship(back_populates="users")
    tenant_memberships: Mapped[list["TenantMembershipRecord"]] = relationship(back_populates="user")
    team_memberships: Mapped[list["TeamMembershipRecord"]] = relationship(back_populates="user")
    created_api_keys: Mapped[list["ApiKeyRecord"]] = relationship(back_populates="created_by_user")
    audit_events: Mapped[list["AuditEventRecord"]] = relationship(back_populates="actor_user")


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
