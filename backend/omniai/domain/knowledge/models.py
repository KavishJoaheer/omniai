from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


DocumentStatus = Literal["PENDING", "PARSING", "PARSED", "EMBEDDING", "INDEXING", "READY", "FAILED", "CANCELLED"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Collection(BaseModel):
    id: str = Field(default_factory=lambda: f"col_{uuid4().hex[:12]}")
    tenant_id: str = ""
    name: str
    description: str | None = None
    embedding_model: str = "text-embedding-default"
    chunk_template: str = "general"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    document_count: int = 0


class Chunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chk_{uuid4().hex[:12]}")
    tenant_id: str = ""
    collection_id: str
    document_id: str
    ordinal: int
    text: str
    char_count: int = 0
    token_count: int = 0
    template_name: str = "general"
    metadata: dict = Field(default_factory=dict)
    indexed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Document(BaseModel):
    id: str = Field(default_factory=lambda: f"doc_{uuid4().hex[:12]}")
    tenant_id: str = ""
    collection_id: str
    name: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    status: DocumentStatus = "PENDING"
    object_key: str | None = None
    parsed_text_key: str | None = None
    content_sha256: str | None = None
    page_count: int = 0
    parser_name: str | None = None
    error_message: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
