from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ChunkSpec:
    text: str
    metadata: dict = field(default_factory=dict)


class ChunkTemplatePort(Protocol):
    name: str

    def chunk(self, *, text: str, document_metadata: dict) -> list[ChunkSpec]: ...
