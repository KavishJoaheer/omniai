from __future__ import annotations

import re

from omniai.ports.chunk_template import ChunkSpec


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_words(text: str) -> list[str]:
    return text.split()


def _words_to_text(words: list[str]) -> str:
    return " ".join(words)


class SmallToBigChunkTemplate:
    """Parent-child chunking for small-to-big retrieval.

    Creates overlapping child chunks (for precise vector search) nested inside
    non-overlapping parent chunks (for rich LLM context). Only child chunks are
    marked is_indexable=True; parent chunks carry is_indexable=False and are only
    fetched when a child hit is expanded.
    """

    name = "small-to-big"

    def __init__(
        self,
        *,
        parent_size: int = 400,
        child_size: int = 100,
        child_overlap: int = 20,
    ) -> None:
        self._parent_size = parent_size
        self._child_size = child_size
        self._child_overlap = child_overlap

    def chunk(self, *, text: str, document_metadata: dict) -> list[ChunkSpec]:
        words = _split_words(text)
        if not words:
            return []

        specs: list[ChunkSpec] = []

        # Build parent windows (no overlap between parents)
        parent_starts = list(range(0, len(words), self._parent_size))
        parents: list[tuple[int, str, str | None]] = []  # (start_word_idx, text, id_placeholder)

        for p_idx, p_start in enumerate(parent_starts):
            parent_words = words[p_start: p_start + self._parent_size]
            parent_text = _words_to_text(parent_words)
            parent_spec = ChunkSpec(
                text=parent_text,
                metadata={
                    **document_metadata,
                    "chunk_kind": "parent",
                    "parent_index": p_idx,
                    "is_indexable": False,
                },
            )
            parents.append((p_start, parent_text, None))
            specs.append(parent_spec)

        # Build child windows with overlap, referencing their parent by list position
        for p_idx, (p_start, parent_text, _) in enumerate(parents):
            parent_end = p_start + self._parent_size
            child_start = p_start
            child_step = max(1, self._child_size - self._child_overlap)

            while child_start < parent_end and child_start < len(words):
                child_words = words[child_start: child_start + self._child_size]
                if not child_words:
                    break
                child_text = _words_to_text(child_words)
                child_spec = ChunkSpec(
                    text=child_text,
                    metadata={
                        **document_metadata,
                        "chunk_kind": "child",
                        "parent_index": p_idx,
                        "is_indexable": True,
                    },
                )
                specs.append(child_spec)
                child_start += child_step

        return specs
