from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from omniai.connectors.base import DiscoveredFile

"""Web-crawler connector.

Crawls one or more seed URLs up to a configurable depth, extracts plain text
via BeautifulSoup, and yields each page as a DiscoveredFile so the ingestion
pipeline can parse and index it.

Config schema
-------------
{
  "urls": ["https://example.com/docs/"],   # required — seed URLs
  "depth": 1,                               # 0 = seed only, 1 = follow links once
  "max_pages": 50,                          # hard cap across the entire crawl
  "allowed_domains": ["example.com"],       # optional whitelist; defaults to seed domains
  "user_agent": "OmniAI-Crawler/1.0",
  "timeout_seconds": 15,
  "include_patterns": [],                   # optional regex allow-list for URLs
  "exclude_patterns": ["#", "?", "login"]  # substrings that cause a URL to be skipped
}
"""

logger = logging.getLogger(__name__)

_DEFAULT_UA = "OmniAI-Crawler/1.0 (internal; +https://omniai.local)"
_DEFAULT_EXCLUDE = {"#", "javascript:", "mailto:", "tel:"}


class WebCrawlerConnector:
    """Depth-limited web crawler that converts HTML pages to plain-text documents.

    Each crawled page becomes one ``DiscoveredFile`` with ``mime_type=text/plain``.
    The filename is derived from the URL path so the knowledge store can display
    a readable label.

    Design decisions
    ----------------
    * Uses ``httpx.AsyncClient`` with a shared connection pool per sync pass.
    * Limits concurrency to 4 simultaneous requests to be polite.
    * Silently skips non-200 responses and non-HTML content types.
    * Does NOT execute JavaScript — only static HTML is processed.
    """

    kind = "web_crawler"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:  # type: ignore[override]
        seed_urls: list[str] = list(config.get("urls") or [])
        if not seed_urls:
            return

        max_depth = int(config.get("depth") or 1)
        max_pages = int(config.get("max_pages") or 50)
        timeout = float(config.get("timeout_seconds") or 15.0)
        user_agent = str(config.get("user_agent") or _DEFAULT_UA)

        # Domain whitelist — defaults to seed domains
        allowed_domains: set[str] = set(config.get("allowed_domains") or [])
        if not allowed_domains:
            for url in seed_urls:
                host = urlparse(url).netloc
                if host:
                    allowed_domains.add(host)

        include_patterns: list[re.Pattern[str]] = [
            re.compile(p) for p in (config.get("include_patterns") or [])
        ]
        exclude_snippets: set[str] = set(config.get("exclude_patterns") or _DEFAULT_EXCLUDE)
        exclude_snippets |= _DEFAULT_EXCLUDE

        visited: set[str] = set()
        # frontier: list of (url, depth)
        frontier: list[tuple[str, int]] = [(u, 0) for u in seed_urls]
        sem = asyncio.Semaphore(4)

        headers = {"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.8"}

        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            verify=False,  # many internal/intranet docs use self-signed certs
        ) as client:
            while frontier and len(visited) < max_pages:
                url, depth = frontier.pop(0)
                url = url.strip()
                if not url or url in visited:
                    continue
                if not _url_allowed(url, allowed_domains, include_patterns, exclude_snippets):
                    continue

                visited.add(url)

                async with sem:
                    html, links = await _fetch_page(client, url)

                if html is None:
                    continue

                text = _extract_text(html)
                if not text.strip():
                    continue

                filename = _url_to_filename(url)
                yield DiscoveredFile(
                    source_id=url,
                    filename=filename,
                    mime_type="text/plain",
                    content=text.encode("utf-8", errors="replace"),
                )

                # Enqueue child links if we have crawl budget left
                if depth < max_depth:
                    for link in links:
                        absolute = urljoin(url, link)
                        # Strip fragment
                        absolute = absolute.split("#")[0]
                        if absolute not in visited:
                            frontier.append((absolute, depth + 1))

    @staticmethod
    def validate_config(config: dict) -> None:
        urls = config.get("urls")
        if not urls or not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise ValueError("web_crawler config requires 'urls' (list of strings).")
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(f"web_crawler: URL must start with http:// or https:// — got {url!r}.")
        depth = config.get("depth", 1)
        if not isinstance(depth, int) or depth < 0 or depth > 5:
            raise ValueError("web_crawler 'depth' must be an integer between 0 and 5.")
        max_pages = config.get("max_pages", 50)
        if not isinstance(max_pages, int) or max_pages < 1 or max_pages > 500:
            raise ValueError("web_crawler 'max_pages' must be between 1 and 500.")


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[str | None, list[str]]:
    """Fetch *url* and return (html_text, discovered_links).

    Returns ``(None, [])`` on any error or non-HTML response.
    """
    try:
        response = await client.get(url)
        if response.status_code != 200:
            logger.debug("web_crawler: skipping %s (HTTP %s)", url, response.status_code)
            return None, []
        ct = response.headers.get("content-type", "")
        if "html" not in ct.lower():
            logger.debug("web_crawler: skipping %s (content-type: %s)", url, ct)
            return None, []
        html = response.text
        # Extract links for depth expansion
        soup = BeautifulSoup(html, "lxml")
        links = [
            tag["href"]
            for tag in soup.find_all("a", href=True)
            if isinstance(tag["href"], str)
        ]
        return html, links
    except Exception as exc:
        logger.warning("web_crawler: fetch failed for %s — %s", url, exc)
        return None, []


def _extract_text(html: str) -> str:
    """Convert HTML to clean plain text, stripping scripts/styles."""
    soup = BeautifulSoup(html, "lxml")
    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    # Get visible text with block-level spacing
    lines: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "pre", "code"]):
        text = element.get_text(separator=" ", strip=True)
        if text:
            lines.append(text)
    if not lines:
        # Fallback: entire body text
        body = soup.find("body")
        return (body or soup).get_text(separator="\n", strip=True)
    return "\n".join(lines)


def _url_to_filename(url: str) -> str:
    """Derive a readable filename from a URL for the knowledge store label."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "index"
    # Take last two path segments to keep it readable but unique-ish
    parts = [p for p in path.split("/") if p]
    stem = "_".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "index")
    # Sanitise
    stem = re.sub(r"[^\w\-.]", "_", stem)[:80]
    return f"{stem}.txt"


def _url_allowed(
    url: str,
    allowed_domains: set[str],
    include_patterns: list[re.Pattern[str]],
    exclude_snippets: set[str],
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if allowed_domains and parsed.netloc not in allowed_domains:
        return False
    if any(snip in url for snip in exclude_snippets):
        return False
    if include_patterns and not any(p.search(url) for p in include_patterns):
        return False
    return True
