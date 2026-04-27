from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ParseResult:
    text: str
    page_count: int = 0
    metadata: dict = field(default_factory=dict)


class DocumentParserPort(Protocol):
    name: str
    mime_types: tuple[str, ...]
    extensions: tuple[str, ...]

    def parse(self, *, data: bytes, filename: str) -> ParseResult: ...
