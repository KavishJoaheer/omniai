from __future__ import annotations

import logging

from omniai.ports.embedding_provider import EmbeddingProviderPort
from omniai.ports.reranker import RerankCandidate

logger = logging.getLogger(__name__)


class PairedEmbeddingReranker:
    """Fallback reranker that uses a bi-encoder embedding model.

    Embeds "query: <q>" alone and "query: <q> passage: <text>" for each candidate,
    then scores each candidate by cosine similarity between the paired vector
    and the anchor query vector. Not a true cross-encoder, but materially
    better than first-stage hybrid search alone, and works with any embedding
    provider we already have configured.
    """

    name = "paired-embedding"

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProviderPort,
        embedding_model: str,
    ) -> None:
        self._embeddings = embedding_provider
        self._model = embedding_model

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[float]:
        if not candidates:
            return []
        try:
            anchor = await self._embeddings.embed(model=self._model, inputs=[f"query: {query}"])
            paired = await self._embeddings.embed(
                model=self._model,
                inputs=[f"query: {query} passage: {c.text[:1500]}" for c in candidates],
            )
        except Exception:
            logger.exception("PairedEmbeddingReranker.embed failed")
            return [0.0] * len(candidates)

        if not anchor or len(paired) != len(candidates):
            return [0.0] * len(candidates)

        anchor_vec = anchor[0]
        return [_cosine(anchor_vec, vec) for vec in paired]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
