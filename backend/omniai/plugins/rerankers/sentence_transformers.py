from __future__ import annotations

import asyncio
import logging
from typing import Any

from omniai.ports.reranker import RerankCandidate

logger = logging.getLogger(__name__)


class SentenceTransformersReranker:
    """Local cross-encoder reranker using the sentence-transformers library.

    Default model: BAAI/bge-reranker-base (110M params, ~440MB, CPU-friendly).

    sentence-transformers is an optional dependency — the constructor raises
    ImportError if not installed. The factory in `factory.py` handles this
    gracefully.
    """

    name = "sentence-transformers"

    def __init__(self, *, model_name: str = "BAAI/bge-reranker-base") -> None:
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model_name = model_name
        self._model: Any = CrossEncoder(model_name)

    async def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[float]:
        if not candidates:
            return []
        pairs = [(query, c.text[:2000]) for c in candidates]
        # CrossEncoder.predict is synchronous CPU-bound; run in a thread to
        # avoid blocking the event loop.
        try:
            scores = await asyncio.to_thread(self._model.predict, pairs)
        except Exception:
            logger.exception("SentenceTransformersReranker.predict failed")
            return [c.text and 0.0 for c in candidates]
        return [float(s) for s in scores]
