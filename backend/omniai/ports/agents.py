from __future__ import annotations

from typing import Protocol

from omniai.domain.agents.models import Agent, AgentRun


class AgentStorePort(Protocol):
    def list_agents(self) -> list[Agent]: ...

    def create_agent(
        self,
        *,
        name: str,
        description: str | None,
        definition: dict,
        template_id: str | None = None,
    ) -> Agent: ...

    def get_agent(self, agent_id: str) -> Agent: ...

    def update_agent(
        self,
        *,
        agent_id: str,
        name: str | None = None,
        description: str | None = None,
        definition: dict | None = None,
        published: bool | None = None,
    ) -> Agent: ...

    def delete_agent(self, agent_id: str) -> None: ...

    def list_runs(self, agent_id: str) -> list[AgentRun]: ...

    def get_run(self, agent_id: str, run_id: str) -> AgentRun: ...

    def create_run(
        self,
        *,
        agent_id: str,
        input_payload: dict,
        replay_of_run_id: str | None = None,
        replay_from_event: int | None = None,
    ) -> AgentRun: ...

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
    ) -> AgentRun: ...
