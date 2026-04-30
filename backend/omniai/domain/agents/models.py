from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from omniai.domain.knowledge.models import utc_now


AgentRunStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: f"agt_{uuid4().hex[:12]}")
    tenant_id: str = ""
    name: str
    description: str | None = None
    definition: dict = Field(default_factory=dict)
    published: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentRun(BaseModel):
    id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    tenant_id: str = ""
    agent_id: str
    status: AgentRunStatus = "QUEUED"
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
