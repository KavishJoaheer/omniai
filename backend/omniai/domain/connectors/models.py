from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from omniai.domain.knowledge.models import utc_now

ConnectorKind = Literal["local_folder", "s3"]


class Connector(BaseModel):
    id: str = Field(default_factory=lambda: f"cnt_{uuid4().hex[:12]}")
    tenant_id: str = ""
    collection_id: str
    name: str
    kind: ConnectorKind
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    sync_interval_seconds: int = 300
    last_sync_at: datetime | None = None
    last_error: str | None = None
    last_synced_count: int = 0
    seen_hashes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConnectorSyncReport(BaseModel):
    connector_id: str
    discovered: int = 0
    ingested: int = 0
    skipped_duplicate: int = 0
    errors: list[str] = Field(default_factory=list)
    finished_at: datetime = Field(default_factory=utc_now)
