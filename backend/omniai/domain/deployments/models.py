from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from omniai.domain.knowledge.models import utc_now

DeploymentKind = Literal["public_chat", "webhook"]
DeploymentTargetKind = Literal["collection", "agent"]
DeploymentStatus = Literal["ACTIVE", "PAUSED", "DELETED"]


class Deployment(BaseModel):
    id: str = Field(default_factory=lambda: f"dep_{uuid4().hex[:12]}")
    tenant_id: str = ""
    name: str
    slug: str
    kind: DeploymentKind = "public_chat"
    target_kind: DeploymentTargetKind = "collection"
    target_id: str
    system_prompt_override: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    anonymous_allowed: bool = True
    rate_limit_per_minute: int = 60
    daily_message_quota: int = 500
    branding: dict = Field(default_factory=dict)
    definition_snapshot: dict = Field(default_factory=dict)
    status: DeploymentStatus = "ACTIVE"
    version: int = 1
    message_count: int = 0
    today_message_count: int = 0
    today_window_start: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
