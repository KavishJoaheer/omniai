from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

JobHandler = Callable[..., Awaitable[None]]


class InlineJobQueue:
    """Runs jobs in-process. Useful for tests and local dev without Redis."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    async def enqueue(self, *, job_name: str, payload: dict) -> str:
        handler = self._handlers.get(job_name)
        job_id = uuid.uuid4().hex
        if handler is None:
            logger.warning("No handler registered for inline job %s", job_name)
            return job_id
        try:
            await handler(**payload)
        except Exception:
            logger.exception("Inline job %s failed", job_name)
        return job_id
