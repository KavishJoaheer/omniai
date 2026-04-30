from __future__ import annotations

from datetime import datetime
from typing import Protocol

from omniai.domain.connectors.models import Connector


class ConnectorStorePort(Protocol):
    def list_connectors(self, *, collection_id: str | None = None) -> list[Connector]: ...

    def create_connector(
        self,
        *,
        collection_id: str,
        name: str,
        kind: str,
        config: dict,
        sync_interval_seconds: int = 300,
    ) -> Connector: ...

    def get_connector(self, connector_id: str) -> Connector: ...

    def update_connector(
        self,
        *,
        connector_id: str,
        name: str | None = None,
        config: dict | None = None,
        enabled: bool | None = None,
        sync_interval_seconds: int | None = None,
    ) -> Connector: ...

    def delete_connector(self, connector_id: str) -> None:
        ...

    def record_sync(
        self,
        *,
        connector_id: str,
        last_sync_at: datetime,
        last_error: str | None,
        last_synced_count: int,
        seen_hashes: list[str],
    ) -> Connector: ...

    def list_enabled_connectors_across_tenants(self) -> list[tuple[str, Connector]]:
        """Returns (tenant_id, Connector) for every enabled connector — for the
        background sync scheduler. Implementations should use a separate session.
        """
        ...
