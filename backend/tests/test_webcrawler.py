"""Tests for the WebCrawlerConnector.

HTTP calls are intercepted via httpx's transport mock so no real network
traffic is generated.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from omniai.connectors.webcrawler import WebCrawlerConnector, _extract_text, _url_to_filename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello Crawler</h1>
  <p>This page talks about <strong>Python</strong> and machine learning.</p>
  <a href="/page2">Next page</a>
  <script>alert('noise')</script>
</body>
</html>"""

PAGE2_HTML = """<!DOCTYPE html>
<html><body>
  <h1>Page Two</h1>
  <p>Depth-one content about neural networks.</p>
</body></html>"""


async def _collect(connector, config):
    out = []
    async for f in connector.discover(config):
        out.append(f)
    return out


def _mock_transport(url_map: dict[str, tuple[int, str]]):
    """Return an httpx.MockTransport that serves HTML from url_map."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("#")[0]
        status, body = url_map.get(url, (404, ""))
        return httpx.Response(status, text=body, headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Unit: text extraction
# ---------------------------------------------------------------------------

def test_extract_text_removes_script_tags():
    text = _extract_text(SIMPLE_HTML)
    assert "alert" not in text


def test_extract_text_includes_heading_and_paragraph():
    text = _extract_text(SIMPLE_HTML)
    assert "Hello Crawler" in text
    assert "Python" in text


def test_extract_text_empty_html():
    assert _extract_text("") == ""


def test_url_to_filename_basic():
    name = _url_to_filename("https://example.com/docs/getting-started")
    assert name.endswith(".txt")
    assert "getting" in name or "started" in name or "docs" in name


def test_url_to_filename_root():
    name = _url_to_filename("https://example.com/")
    assert name.endswith(".txt")


# ---------------------------------------------------------------------------
# Unit: config validation
# ---------------------------------------------------------------------------

def test_validate_config_requires_urls():
    with pytest.raises(ValueError, match="urls"):
        WebCrawlerConnector.validate_config({})


def test_validate_config_rejects_non_http():
    with pytest.raises(ValueError, match="http"):
        WebCrawlerConnector.validate_config({"urls": ["ftp://example.com"], "depth": 1, "max_pages": 10})


def test_validate_config_rejects_depth_out_of_range():
    with pytest.raises(ValueError, match="depth"):
        WebCrawlerConnector.validate_config({"urls": ["https://example.com"], "depth": 99, "max_pages": 10})


def test_validate_config_accepts_valid():
    WebCrawlerConnector.validate_config({"urls": ["https://example.com"], "depth": 1, "max_pages": 20})


# ---------------------------------------------------------------------------
# Integration: discover with mocked HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discover_seed_url_yields_file():
    """Depth-0 crawl returns exactly the seed page."""
    transport_map = {"https://example.com/": (200, SIMPLE_HTML)}
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/"],
            "depth": 0,
            "max_pages": 5,
        })
    assert len(files) == 1
    content = files[0].content.decode()
    assert "Hello Crawler" in content
    assert files[0].mime_type == "text/plain"


@pytest.mark.asyncio
async def test_discover_depth_1_follows_links():
    """Depth-1 crawl should follow <a href> links found on the seed page."""
    transport_map = {
        "https://example.com/": (200, SIMPLE_HTML),
        "https://example.com/page2": (200, PAGE2_HTML),
    }
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/"],
            "depth": 1,
            "max_pages": 10,
            "allowed_domains": ["example.com"],
        })
    urls_crawled = {f.source_id for f in files}
    assert "https://example.com/" in urls_crawled
    assert "https://example.com/page2" in urls_crawled


@pytest.mark.asyncio
async def test_discover_max_pages_caps_results():
    """Crawl stops after max_pages regardless of remaining frontier."""
    # Seed has links to /p1 through /p10
    links = "".join(f'<a href="/p{i}">link {i}</a>' for i in range(10))
    seed_html = f"<html><body><p>index</p>{links}</body></html>"
    page_html = "<html><body><p>content</p></body></html>"

    transport_map: dict[str, tuple[int, str]] = {
        "https://example.com/": (200, seed_html),
        **{f"https://example.com/p{i}": (200, page_html) for i in range(10)},
    }
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/"],
            "depth": 1,
            "max_pages": 3,
            "allowed_domains": ["example.com"],
        })
    assert len(files) <= 3


@pytest.mark.asyncio
async def test_discover_skips_404_pages():
    """Non-200 responses should not produce DiscoveredFile entries."""
    transport_map = {"https://example.com/missing": (404, "")}
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/missing"],
            "depth": 0,
            "max_pages": 5,
        })
    assert files == []


@pytest.mark.asyncio
async def test_discover_deduplicates_urls():
    """The same URL should only be crawled once even if linked multiple times."""
    seed_html = '<html><body><a href="/">home</a><a href="/">home again</a></body></html>'
    transport_map = {"https://example.com/": (200, seed_html)}
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/"],
            "depth": 1,
            "max_pages": 10,
        })
    # Deduplicated — only one file for the seed URL
    source_ids = [f.source_id for f in files]
    assert len(source_ids) == len(set(source_ids))


@pytest.mark.asyncio
async def test_discover_respects_domain_whitelist():
    """External links (off-domain) must be ignored."""
    seed_html = '<html><body><a href="https://evil.com/harvest">external</a><p>local content</p></body></html>'
    transport_map = {
        "https://example.com/": (200, seed_html),
        "https://evil.com/harvest": (200, "<html><body>should not appear</body></html>"),
    }
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/"],
            "depth": 1,
            "max_pages": 10,
            "allowed_domains": ["example.com"],
        })
    assert all(f.source_id.startswith("https://example.com") for f in files)


@pytest.mark.asyncio
async def test_discover_empty_page_not_yielded():
    """Pages that produce empty text after extraction are silently skipped."""
    empty_html = "<html><head></head><body><script>var x=1;</script></body></html>"
    transport_map = {"https://example.com/empty": (200, empty_html)}
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=_mock_transport(transport_map))):
        connector = WebCrawlerConnector()
        files = await _collect(connector, {
            "urls": ["https://example.com/empty"],
            "depth": 0,
            "max_pages": 5,
        })
    assert files == []
