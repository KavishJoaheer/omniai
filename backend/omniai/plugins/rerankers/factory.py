from __future__ import annotations

import logging

from omniai.config.settings import Settings
from omniai.plugins.rerankers.paired_embedding import PairedEmbeddingReranker
from omniai.ports.embedding_provider import EmbeddingProviderPort
from omniai.ports.reranker import RerankerPort

logger = logging.getLogger(__name__)


def build_reranker(
    *,
    settings: Settings,
    embedding_provider: EmbeddingProviderPort,
    embedding_model: str,
) -> RerankerPort:
    """Build the best reranker available given settings + installed packages.

    Resolution order:
      1. settings.reranker_kind == "sentence-transformers" → load BGE cross-encoder
      2. anything else → PairedEmbeddingReranker (always works)
    """
    kind = (getattr(settings, "reranker_kind", "") or "paired").lower()
    if kind in ("sentence-transformers", "cross-encoder", "bge"):
        try:
            from omniai.plugins.rerankers.sentence_transformers import SentenceTransformersReranker

            model_name = getattr(settings, "reranker_model", "") or "BAAI/bge-reranker-base"
            logger.info("reranker: using sentence-transformers (%s)", model_name)
            return SentenceTransformersReranker(model_name=model_name)
        except ImportError:
            logger.warning(
                "reranker: sentence-transformers not installed, falling back to paired-embedding"
            )

    return PairedEmbeddingReranker(
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
