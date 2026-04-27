from __future__ import annotations

from typing import Protocol


class JobQueuePort(Protocol):
    async def enqueue(self, *, job_name: str, payload: dict) -> str: ...
