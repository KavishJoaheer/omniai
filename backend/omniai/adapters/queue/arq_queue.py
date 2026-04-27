from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings


class ArqJobQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        return self._pool

    async def enqueue(self, *, job_name: str, payload: dict) -> str:
        pool = await self._get_pool()
        job = await pool.enqueue_job(job_name, **payload)
        if job is None:
            raise RuntimeError(f"Arq refused job {job_name}")
        return job.job_id
