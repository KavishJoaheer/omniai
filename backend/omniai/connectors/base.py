from __future__ import annotations

import hashlib
import logging
import mimetypes
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DiscoveredFile:
    """A file produced by a connector during a sync pass.

    `source_id` is the connector's stable identifier for the file (path, S3 key,
    file id, etc.) — used in log lines and to surface failures.
    `content` may be loaded lazily by the connector; the service is responsible
    for hashing it and deduplicating against previously-seen hashes.
    """

    source_id: str
    filename: str
    mime_type: str
    content: bytes


class ConnectorAdapter(Protocol):
    """Adapter that turns a configured connector into a stream of files to ingest.

    Implementations should be safe to call repeatedly — sync passes happen on a
    schedule. They do NOT need to deduplicate themselves; the ConnectorService
    handles dedup using sha256 hashes stored on the connector row.
    """

    kind: str

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]: ...


def hash_content(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or fallback
