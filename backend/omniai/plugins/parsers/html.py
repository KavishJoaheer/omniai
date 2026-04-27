from __future__ import annotations

from bs4 import BeautifulSoup

from omniai.ports.parser import ParseResult


class HtmlParser:
    name = "html"
    mime_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")
    extensions: tuple[str, ...] = (".html", ".htm", ".xhtml")

    def parse(self, *, data: bytes, filename: str) -> ParseResult:
        soup = BeautifulSoup(data, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        return ParseResult(
            text=text,
            page_count=1,
            metadata={"filename": filename, "title": title},
        )
