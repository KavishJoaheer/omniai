from __future__ import annotations

from omniai.adapters.queue.arq_queue import ArqJobQueue
from omniai.adapters.queue.inline import InlineJobQueue
from omniai.config.settings import Settings


def build_job_queue(settings: Settings) -> InlineJobQueue | ArqJobQueue:
    if settings.worker_inline or not settings.redis_url:
        return InlineJobQueue()
    return ArqJobQueue(settings.redis_url)
