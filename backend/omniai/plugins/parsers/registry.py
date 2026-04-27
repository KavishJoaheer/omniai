from __future__ import annotations

import os

from omniai.plugins.parsers.docx import DocxParser
from omniai.plugins.parsers.html import HtmlParser
from omniai.plugins.parsers.pdf import PdfParser
from omniai.plugins.parsers.text import CsvParser, PlainTextParser
from omniai.ports.parser import DocumentParserPort


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParserPort] = []
        self._by_mime: dict[str, DocumentParserPort] = {}
        self._by_ext: dict[str, DocumentParserPort] = {}

    def register(self, parser: DocumentParserPort) -> None:
        self._parsers.append(parser)
        for mime in parser.mime_types:
            self._by_mime[mime.lower()] = parser
        for ext in parser.extensions:
            self._by_ext[ext.lower()] = parser

    def supported_mime_types(self) -> set[str]:
        return set(self._by_mime.keys())

    def supported_extensions(self) -> set[str]:
        return set(self._by_ext.keys())

    def resolve(self, *, mime_type: str, filename: str) -> DocumentParserPort | None:
        candidate = self._by_mime.get((mime_type or "").lower())
        if candidate is not None:
            return candidate
        ext = os.path.splitext(filename)[1].lower()
        return self._by_ext.get(ext)


def build_default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PlainTextParser())
    registry.register(CsvParser())
    registry.register(HtmlParser())
    registry.register(PdfParser())
    registry.register(DocxParser())
    return registry
