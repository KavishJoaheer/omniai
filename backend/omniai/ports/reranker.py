from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class RerankCandidate:
    chunk_id: str
    text: str


class RerankerPort(Protocol):
    """A second-stage relevance scorer.

    Implementations score (query, passage) pairs and return a list of scores
    aligned with the input candidates. Higher score = more relevant.
    Implementations should be safe to call concurrently.
    """

    name: str

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[float]: ...
