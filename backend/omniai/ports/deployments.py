from __future__ import annotations

from typing import Protocol

from omniai.domain.deployments.models import Deployment


class DeploymentStorePort(Protocol):
    def list_deployments(self) -> list[Deployment]: ...

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
    ) -> Deployment: ...

    def get_deployment(self, deployment_id: str) -> Deployment: ...

    def get_deployment_by_slug(self, slug: str) -> tuple[str, Deployment] | None:
        """Cross-tenant slug lookup for the public surface — returns (tenant_id, Deployment)."""
        ...

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
    ) -> Deployment: ...

    def delete_deployment(self, deployment_id: str) -> None: ...

    def increment_message_counters(self, deployment_id: str) -> Deployment: ...
