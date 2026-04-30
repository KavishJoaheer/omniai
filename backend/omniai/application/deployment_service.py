from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from omniai.domain.deployments.models import Deployment
from omniai.ports.deployments import DeploymentStorePort

# Slug must be URL-safe and short; reserved prefixes prevent route collisions.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_RESERVED_SLUGS = frozenset({"v1", "api", "admin", "health", "metrics", "auth", "c"})


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not base:
        base = "deployment"
    return base[:48]


def _random_suffix() -> str:
    return secrets.token_urlsafe(4).lower().replace("-", "").replace("_", "")[:6]


def validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise ValueError(
            "Slug must be 3–63 chars, lowercase letters/digits/hyphens, "
            "starting with a letter or digit."
        )
    if slug in _RESERVED_SLUGS:
        raise ValueError(f"Slug {slug!r} is reserved.")


class DeploymentQuotaExceeded(RuntimeError):
    """Raised by the public surface when a deployment is over its daily cap."""


class DeploymentService:
    """Tenant-scoped deploy manager.

    Wraps the storage port with the rules an owner needs:
      - generate URL-safe slugs
      - snapshot the target's current config so editing the agent later does
        NOT silently change a published deployment
      - guard quota / status before each public message
    """

    def __init__(
        self,
        *,
        store: DeploymentStorePort,
        tenant_id: str,
    ) -> None:
        self._store = store
        self._tenant_id = tenant_id

    # ---- CRUD ----------------------------------------------------------------

    def list(self) -> list[Deployment]:
        return self._store.list_deployments()

    def get(self, deployment_id: str) -> Deployment:
        return self._store.get_deployment(deployment_id)

    def create(
        self,
        *,
        name: str,
        kind: str,
        target_kind: str,
        target_id: str,
        slug: str | None = None,
        system_prompt_override: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        anonymous_allowed: bool = True,
        rate_limit_per_minute: int = 60,
        daily_message_quota: int = 500,
        branding: dict | None = None,
        definition_snapshot: dict | None = None,
    ) -> Deployment:
        if kind not in ("public_chat", "webhook"):
            raise ValueError(f"Unsupported deployment kind: {kind!r}")
        if target_kind not in ("collection", "agent"):
            raise ValueError(f"Unsupported target_kind: {target_kind!r}")

        final_slug = slug or f"{_slugify(name)}-{_random_suffix()}"
        validate_slug(final_slug)
        return self._store.create_deployment(
            name=name,
            slug=final_slug,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            system_prompt_override=system_prompt_override,
            model_provider=model_provider,
            model_name=model_name,
            anonymous_allowed=anonymous_allowed,
            rate_limit_per_minute=rate_limit_per_minute,
            daily_message_quota=daily_message_quota,
            branding=branding or {},
            definition_snapshot=definition_snapshot or {},
        )

    def update(
        self,
        deployment_id: str,
        *,
        name: str | None = None,
        system_prompt_override: str | None = None,
        anonymous_allowed: bool | None = None,
        rate_limit_per_minute: int | None = None,
        daily_message_quota: int | None = None,
        branding: dict | None = None,
        status: str | None = None,
    ) -> Deployment:
        return self._store.update_deployment(
            deployment_id=deployment_id,
            name=name,
            system_prompt_override=system_prompt_override,
            anonymous_allowed=anonymous_allowed,
            rate_limit_per_minute=rate_limit_per_minute,
            daily_message_quota=daily_message_quota,
            branding=branding,
            status=status,
        )

    def pause(self, deployment_id: str) -> Deployment:
        return self.update(deployment_id, status="PAUSED")

    def resume(self, deployment_id: str) -> Deployment:
        return self.update(deployment_id, status="ACTIVE")

    def delete(self, deployment_id: str) -> None:
        self._store.delete_deployment(deployment_id)

    # ---- Public-surface helpers ---------------------------------------------

    @staticmethod
    def assert_active(deployment: Deployment) -> None:
        if deployment.status != "ACTIVE":
            raise DeploymentQuotaExceeded(f"Deployment is {deployment.status.lower()}.")

    @staticmethod
    def assert_within_daily_quota(deployment: Deployment) -> None:
        if deployment.daily_message_quota <= 0:
            return  # 0 means unlimited
        now = datetime.now(timezone.utc)
        # If we're in a new day, the increment helper will reset; treat as 0.
        if deployment.today_window_start is None or deployment.today_window_start.date() != now.date():
            return
        if deployment.today_message_count >= deployment.daily_message_quota:
            raise DeploymentQuotaExceeded(
                f"Daily message quota of {deployment.daily_message_quota} reached for this deployment."
            )

    def increment_counters(self, deployment_id: str) -> Deployment:
        # Re-fetch so we always work off fresh counts
        return self._store.increment_message_counters(deployment_id)
