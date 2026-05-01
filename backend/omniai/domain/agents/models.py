from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from omniai.domain.knowledge.models import utc_now


# M20: added PAUSED for human-in-the-loop
AgentRunStatus = Literal["QUEUED", "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: f"agt_{uuid4().hex[:12]}")
    tenant_id: str = ""
    name: str
    description: str | None = None
    definition: dict = Field(default_factory=dict)
    published: bool = False
    # M20: marketplace / import tracking
    template_id: str | None = None
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
    # M20: human-in-the-loop — node that paused the run
    paused_at_node: str | None = None
    # M20: resume payload injected by the human
    resumed_with: dict = Field(default_factory=dict)
    # M20: time-travel — which run + event offset this was forked from
    replay_of_run_id: str | None = None
    replay_from_event: int | None = None
    # M20: cost tracking
    cost_usd: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
