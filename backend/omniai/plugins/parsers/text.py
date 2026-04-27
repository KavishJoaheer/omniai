from __future__ import annotations

import csv
import io

from omniai.ports.parser import ParseResult


class PlainTextParser:
    name = "text"
    mime_types: tuple[str, ...] = (
        "text/plain",
        "text/markdown",
        "text/x-markdown",
    )
    extensions: tuple[str, ...] = (".txt", ".md", ".markdown", ".log")

    def parse(self, *, data: bytes, filename: str) -> ParseResult:
        text = _decode(data)
        return ParseResult(text=text, page_count=1, metadata={"filename": filename})


class CsvParser:
    name = "csv"
    mime_types: tuple[str, ...] = ("text/csv", "application/csv")
    extensions: tuple[str, ...] = (".csv", ".tsv")

    def parse(self, *, data: bytes, filename: str) -> ParseResult:
        text = _decode(data)
        delimiter = "\t" if filename.lower().endswith(".tsv") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        if not rows:
            return ParseResult(text="", page_count=1, metadata={"row_count": 0})
        header = rows[0]
        body = rows[1:]
        rendered_lines: list[str] = []
        for row in body:
            cells = [f"{header[i]}: {row[i]}" for i in range(min(len(header), len(row)))]
            rendered_lines.append("; ".join(cells))
        return ParseResult(
            text="\n".join(rendered_lines),
            page_count=1,
            metadata={"row_count": len(body), "column_count": len(header)},
        )


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
