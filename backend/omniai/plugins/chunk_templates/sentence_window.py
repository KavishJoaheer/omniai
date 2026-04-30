from __future__ import annotations

import re

from omniai.ports.chunk_template import ChunkSpec

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)", re.MULTILINE)


class SentenceWindowChunkTemplate:
    name = "sentence-window"

    def __init__(self, *, window_radius: int = 2) -> None:
        self._window_radius = max(0, window_radius)

    def chunk(self, *, text: str, document_metadata: dict) -> list[ChunkSpec]:
        sentences = _split_sentences(text)
        if not sentences:
            return []

        specs: list[ChunkSpec] = []
        for index, sentence in enumerate(sentences):
            start = max(0, index - self._window_radius)
            end = min(len(sentences), index + self._window_radius + 1)
            window_text = " ".join(sentences[start:end])
            specs.append(
                ChunkSpec(
                    text=window_text,
                    metadata={
                        **document_metadata,
                        "chunk_kind": "parent",
                        "parent_index": index,
                        "sentence_start": start,
                        "sentence_end": end - 1,
                        "is_indexable": False,
                    },
                )
            )
            specs.append(
                ChunkSpec(
                    text=sentence,
                    metadata={
                        **document_metadata,
                        "chunk_kind": "child",
                        "parent_index": index,
                        "sentence_index": index,
                        "is_indexable": True,
                    },
                )
            )
        return specs


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for match in _SENTENCE_RE.finditer(text):
        sentence = " ".join(match.group(0).split())
        if sentence:
            sentences.append(sentence)
    if not sentences and text.strip():
        sentences.append(" ".join(text.split()))
    return sentences
