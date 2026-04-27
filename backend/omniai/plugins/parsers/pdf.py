from __future__ import annotations

import io

from pypdf import PdfReader

from omniai.ports.parser import ParseResult


class PdfParser:
    name = "pdf"
    mime_types: tuple[str, ...] = ("application/pdf",)
    extensions: tuple[str, ...] = (".pdf",)

    def parse(self, *, data: bytes, filename: str) -> ParseResult:
        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append(text.strip())
        full_text = "\n\n".join(p for p in pages if p)
        return ParseResult(
            text=full_text,
            page_count=len(reader.pages),
            metadata={"filename": filename},
        )
