"""M17 — Confluence connector.

Ingests Confluence pages via the Confluence REST API v2.  Supports both
cloud (``https://<site>.atlassian.net``) and server/data-centre instances.
Only requires ``httpx``.

Config schema
-------------
{
  "base_url":   "https://mycompany.atlassian.net",   # required
  "username":   "user@example.com",                  # required (basic auth)
  "api_token":  "<Atlassian API token>",             # required
  "space_keys": ["DEV", "OPS"],                      # optional; all spaces if omitted
  "max_pages":  500                                  # optional safety cap
}

For on-prem Confluence Server, use a Personal Access Token in ``api_token``
and set ``username`` to an empty string (PAT auth is Bearer, not Basic).
"""
from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator

import httpx

from omniai.connectors.base import DiscoveredFile

logger = logging.getLogger(__name__)

_MAX_PAGES = 500
_PAGE_SIZE = 50


class ConfluenceConnector:
    """Stream Confluence pages as plain-text documents.

    Config keys:
    - ``base_url`` (str): Confluence base URL (required)
    - ``username`` (str): login email (required for cloud, empty for PAT)
    - ``api_token`` (str): Atlassian API token or PAT (required)
    - ``space_keys`` (list[str]): spaces to sync (optional; all if omitted)
    - ``max_pages`` (int): safety cap (default 500)
    """

    kind = "confluence"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        base_url = config["base_url"].rstrip("/")
        username = config.get("username", "")
        api_token = config["api_token"]
        space_keys = config.get("space_keys") or []
        max_pages = int(config.get("max_pages") or _MAX_PAGES)

        # Build auth header: Basic for cloud, Bearer for PAT
        if username:
            creds = base64.b64encode(f"{username}:{api_token}".encode()).decode()
            auth_header = f"Basic {creds}"
        else:
            auth_header = f"Bearer {api_token}"

        headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
        }

        seen = 0
        async with httpx.AsyncClient(timeout=30, base_url=base_url) as client:
            if space_keys:
                for space_key in space_keys:
                    async for df in _fetch_space_pages(client, headers, space_key, max_pages - seen):
                        if seen >= max_pages:
                            break
                        seen += 1
                        yield df
            else:
                async for df in _fetch_all_pages(client, headers, max_pages - seen):
                    if seen >= max_pages:
                        break
                    seen += 1
                    yield df

    @staticmethod
    def validate_config(config: dict) -> None:
        for key in ("base_url", "api_token"):
            if not config.get(key):
                raise ValueError(f"confluence config requires '{key}'.")
        base_url = config["base_url"]
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("confluence config: 'base_url' must start with http:// or https://")


async def _fetch_space_pages(
    client: httpx.AsyncClient,
    headers: dict,
    space_key: str,
    limit: int,
) -> AsyncIterator[DiscoveredFile]:
    start = 0
    fetched = 0

    while fetched < limit:
        batch = min(_PAGE_SIZE, limit - fetched)
        try:
            resp = await client.get(
                "/wiki/rest/api/content",
                headers=headers,
                params={
                    "spaceKey": space_key,
                    "type": "page",
                    "status": "current",
                    "expand": "body.storage,title,space",
                    "start": start,
                    "limit": batch,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("confluence: fetch space %s failed: %s", space_key, exc)
            break

        results = data.get("results", [])
        for page in results:
            if fetched >= limit:
                break
            df = _page_to_file(page)
            if df:
                fetched += 1
                yield df

        size = data.get("size", 0)
        start += size
        if size < batch:
            break  # no more pages


async def _fetch_all_pages(
    client: httpx.AsyncClient,
    headers: dict,
    limit: int,
) -> AsyncIterator[DiscoveredFile]:
    start = 0
    fetched = 0

    while fetched < limit:
        batch = min(_PAGE_SIZE, limit - fetched)
        try:
            resp = await client.get(
                "/wiki/rest/api/content",
                headers=headers,
                params={
                    "type": "page",
                    "status": "current",
                    "expand": "body.storage,title,space",
                    "start": start,
                    "limit": batch,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("confluence: fetch all pages failed: %s", exc)
            break

        results = data.get("results", [])
        for page in results:
            if fetched >= limit:
                break
            df = _page_to_file(page)
            if df:
                fetched += 1
                yield df

        size = data.get("size", 0)
        start += size
        if size < batch:
            break


def _page_to_file(page: dict) -> DiscoveredFile | None:
    page_id = page.get("id", "")
    title = page.get("title", page_id)

    # Extract storage body (HTML)
    body_storage = page.get("body", {}).get("storage", {}).get("value", "")
    if not body_storage:
        return None

    # Strip HTML tags to get plain text (simple regex-based strip)
    import re
    plain = re.sub(r"<[^>]+>", " ", body_storage)
    plain = re.sub(r"\s+", " ", plain).strip()

    space_key = page.get("space", {}).get("key", "")
    content = f"# {title}\n\nSpace: {space_key}\n\n{plain}".encode("utf-8")

    return DiscoveredFile(
        source_id=f"confluence:{page_id}",
        filename=f"{_safe_filename(title)}.txt",
        mime_type="text/plain",
        content=content,
    )


def _safe_filename(title: str) -> str:
    import re
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    return safe[:128] or "untitled"
