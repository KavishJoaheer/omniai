from __future__ import annotations

import re

from omniai.ports.chunk_template import ChunkSpec


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class QaChunkTemplate:
    name = "qa"

    def __init__(self, *, max_chars: int = 1800) -> None:
        self._max = max_chars

    def chunk(self, *, text: str, document_metadata: dict) -> list[ChunkSpec]:
        text = text.strip()
        if not text:
            return []

        matches = list(_HEADING.finditer(text))
        if not matches:
            return [ChunkSpec(text=text, metadata={"template": self.name})]

        sections: list[ChunkSpec] = []
        for i, match in enumerate(matches):
            heading = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) <= self._max:
                sections.append(
                    ChunkSpec(text=body, metadata={"template": self.name, "heading": heading})
                )
                continue
            for offset in range(0, len(body), self._max):
                sections.append(
                    ChunkSpec(
                        text=body[offset : offset + self._max],
                        metadata={"template": self.name, "heading": heading, "split": True},
                    )
                )
        return sections
