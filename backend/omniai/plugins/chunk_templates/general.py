from __future__ import annotations

import re

from omniai.ports.chunk_template import ChunkSpec


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    return parts or [text.strip()]


class GeneralChunkTemplate:
    name = "general"

    def __init__(self, *, target_chars: int = 1200, overlap_chars: int = 150) -> None:
        self._target = target_chars
        self._overlap = overlap_chars

    def chunk(self, *, text: str, document_metadata: dict) -> list[ChunkSpec]:
        text = text.strip()
        if not text:
            return []

        paragraphs = _split_paragraphs(text)
        chunks: list[ChunkSpec] = []
        buffer: list[str] = []
        buffer_len = 0

        for para in paragraphs:
            para_len = len(para)
            if buffer_len + para_len + 2 <= self._target or not buffer:
                buffer.append(para)
                buffer_len += para_len + 2
                continue

            chunks.append(self._flush(buffer))
            tail = self._tail_for_overlap(buffer)
            buffer = [tail, para] if tail else [para]
            buffer_len = sum(len(p) + 2 for p in buffer)

        if buffer:
            chunks.append(self._flush(buffer))

        return chunks

    def _flush(self, buffer: list[str]) -> ChunkSpec:
        joined = "\n\n".join(buffer)
        return ChunkSpec(text=joined, metadata={"template": self.name})

    def _tail_for_overlap(self, buffer: list[str]) -> str:
        if self._overlap <= 0 or not buffer:
            return ""
        last = buffer[-1]
        return last[-self._overlap :] if len(last) > self._overlap else last
