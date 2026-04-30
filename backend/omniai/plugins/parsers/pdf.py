from __future__ import annotations

import io
import logging
import re

from pypdf import PdfReader

from omniai.ports.parser import ParseResult

logger = logging.getLogger(__name__)


# Sentinel that the indexing worker scans for to attach page numbers to chunks.
# Format: "[OMNI_PAGE_<N>]" wrapped in newlines so it survives chunkers that
# normalize whitespace but never gets joined into adjacent words.
PAGE_MARKER_RE = re.compile(r"\[OMNI_PAGE_(\d+)\]")


def page_marker(page_num: int) -> str:
    return f"\n\n[OMNI_PAGE_{page_num}]\n\n"

# pdfplumber is the table-extraction path. If not installed, we silently fall
# back to pypdf-only text extraction.
try:
    import pdfplumber  # type: ignore

    _HAS_PDFPLUMBER = True
except ImportError:  # pragma: no cover
    _HAS_PDFPLUMBER = False


class PdfParser:
    name = "pdf"
    mime_types: tuple[str, ...] = ("application/pdf",)
    extensions: tuple[str, ...] = (".pdf",)

    def __init__(
        self,
        *,
        ocr_backend=None,
        ocr_min_chars_per_page: int = 50,
        ocr_image_dpi: int = 200,
    ) -> None:
        self._ocr_backend = ocr_backend
        self._ocr_min_chars = max(0, ocr_min_chars_per_page)
        self._ocr_dpi = max(72, ocr_image_dpi)

    def parse(self, *, data: bytes, filename: str) -> ParseResult:
        if _HAS_PDFPLUMBER:
            return self._parse_with_pdfplumber(data=data, filename=filename)
        return self._parse_with_pypdf(data=data, filename=filename)

    def _parse_with_pdfplumber(self, *, data: bytes, filename: str) -> ParseResult:
        """Layout-aware extraction with pdfplumber: text + tables rendered as Markdown.

        Each page's content is preceded by a `[OMNI_PAGE_N]` marker so the
        indexing worker can later tag each chunk with the page it came from.
        Pages that yield very little text are sent through the OCR backend
        (when configured) — useful for scanned/image-only PDFs.
        """
        sections: list[str] = []
        page_count = 0
        ocr_pages_used = 0
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                page_count = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_text = (page.extract_text() or "").strip()
                    tables = []
                    try:
                        tables = page.extract_tables() or []
                    except Exception:
                        tables = []

                    # OCR fallback when text is sparse (likely scanned page)
                    if (
                        self._ocr_backend is not None
                        and len(page_text) < self._ocr_min_chars
                    ):
                        ocr_text = self._ocr_page(page)
                        if ocr_text:
                            page_text = ocr_text
                            ocr_pages_used += 1

                    page_blocks: list[str] = []
                    if page_text:
                        page_blocks.append(page_text)
                    for table_idx, table in enumerate(tables):
                        if not table:
                            continue
                        rendered = _render_table_as_markdown(table)
                        if rendered:
                            page_blocks.append(f"\n[Table {page_num}.{table_idx + 1}]\n{rendered}")

                    if page_blocks:
                        sections.append(page_marker(page_num) + "\n\n".join(page_blocks))
        except Exception as exc:
            logger.warning("pdfplumber failed on %s, falling back to pypdf: %s", filename, exc)
            return self._parse_with_pypdf(data=data, filename=filename)

        full_text = "\n\n".join(sections).strip()
        extractor = "pdfplumber+ocr" if ocr_pages_used else "pdfplumber"
        return ParseResult(
            text=full_text,
            page_count=page_count,
            metadata={
                "filename": filename,
                "extractor": extractor,
                "ocr_pages": ocr_pages_used,
            },
        )

    def _ocr_page(self, page) -> str:
        """Render the page to PNG and run the configured OCR backend on it."""
        try:
            page_image = page.to_image(resolution=self._ocr_dpi)
            buf = io.BytesIO()
            page_image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
        except Exception:
            logger.exception("ocr: failed to render page image")
            return ""
        return self._ocr_backend.extract(png_bytes)

    def _parse_with_pypdf(self, *, data: bytes, filename: str) -> ParseResult:
        reader = PdfReader(io.BytesIO(data))
        sections: list[str] = []
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                text = ""
            if text:
                sections.append(page_marker(page_num) + text)
        full_text = "\n\n".join(sections).strip()
        return ParseResult(
            text=full_text,
            page_count=len(reader.pages),
            metadata={"filename": filename, "extractor": "pypdf"},
        )


def _render_table_as_markdown(table: list[list[str | None]]) -> str:
    """Render a 2D list of cells as a GitHub-flavored Markdown table.

    First row is treated as the header. Cells are stripped and None becomes "".
    Returns "" for empty/degenerate tables.
    """
    rows = [[(cell or "").strip().replace("\n", " ").replace("|", "\\|") for cell in row] for row in table if row]
    if not rows or not rows[0]:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join("---" for _ in range(width)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([header, separator, *body])
