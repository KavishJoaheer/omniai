"""M17 — Notion connector.

Ingests Notion pages and database entries via the official Notion API.
Only requires ``httpx`` (already available in the project).

Config schema
-------------
{
  "api_key":      "<Notion integration token>",       # required
  "database_ids": ["<db-id-1>", "<db-id-2>"],        # optional; searches all if omitted
  "page_ids":     ["<page-id-1>"],                    # optional explicit pages
  "max_pages":    500                                 # optional safety cap
}
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from omniai.connectors.base import DiscoveredFile

logger = logging.getLogger(__name__)

_NOTION_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_MAX_PAGES = 500


class NotionConnector:
    """Stream Notion pages into the ingestion pipeline.

    Walks database query results and/or explicit page IDs, then fetches
    each page's block tree and renders it as plain text.

    Config keys:
    - ``api_key`` (str): Notion integration token (required)
    - ``database_ids`` (list[str]): databases to sync (optional)
    - ``page_ids`` (list[str]): explicit page IDs to sync (optional)
    - ``max_pages`` (int): safety cap (default 500)
    """

    kind = "notion"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        api_key = config["api_key"]
        max_pages = int(config.get("max_pages") or _MAX_PAGES)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

        seen = 0
        async with httpx.AsyncClient(timeout=30) as client:

            # Explicit page IDs
            for page_id in config.get("page_ids") or []:
                if seen >= max_pages:
                    break
                result = await _fetch_page_as_text(client, headers, page_id)
                if result:
                    seen += 1
                    yield result

            # Database entries
            for db_id in config.get("database_ids") or []:
                async for df in _query_database(client, headers, db_id, max_pages - seen):
                    if seen >= max_pages:
                        break
                    seen += 1
                    yield df

            # If no explicit ids/databases, search for all shared pages
            if not config.get("page_ids") and not config.get("database_ids"):
                async for df in _search_all(client, headers, max_pages - seen):
                    if seen >= max_pages:
                        break
                    seen += 1
                    yield df

    @staticmethod
    def validate_config(config: dict) -> None:
        if not config.get("api_key"):
            raise ValueError("notion config requires 'api_key'.")


async def _fetch_page_as_text(
    client: httpx.AsyncClient,
    headers: dict,
    page_id: str,
) -> DiscoveredFile | None:
    try:
        resp = await client.get(f"{_NOTION_BASE}/pages/{page_id}", headers=headers)
        resp.raise_for_status()
        page = resp.json()
    except Exception as exc:
        logger.warning("notion: fetch page %s failed: %s", page_id, exc)
        return None

    title = _extract_title(page)
    blocks_text = await _fetch_blocks_text(client, headers, page_id)

    content = f"# {title}\n\n{blocks_text}".encode("utf-8")
    return DiscoveredFile(
        source_id=f"notion:{page_id}",
        filename=f"{_safe_filename(title)}.md",
        mime_type="text/markdown",
        content=content,
    )


async def _query_database(
    client: httpx.AsyncClient,
    headers: dict,
    database_id: str,
    limit: int,
) -> AsyncIterator[DiscoveredFile]:
    cursor: str | None = None
    fetched = 0

    while fetched < limit:
        payload: dict = {"page_size": min(100, limit - fetched)}
        if cursor:
            payload["start_cursor"] = cursor

        try:
            resp = await client.post(
                f"{_NOTION_BASE}/databases/{database_id}/query",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("notion: query database %s failed: %s", database_id, exc)
            break

        for page in data.get("results", []):
            if fetched >= limit:
                break
            result = await _fetch_page_as_text(client, headers, page["id"])
            if result:
                fetched += 1
                yield result

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")


async def _search_all(
    client: httpx.AsyncClient,
    headers: dict,
    limit: int,
) -> AsyncIterator[DiscoveredFile]:
    cursor: str | None = None
    fetched = 0

    while fetched < limit:
        payload: dict = {
            "filter": {"value": "page", "property": "object"},
            "page_size": min(100, limit - fetched),
        }
        if cursor:
            payload["start_cursor"] = cursor

        try:
            resp = await client.post(
                f"{_NOTION_BASE}/search",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("notion: search failed: %s", exc)
            break

        for item in data.get("results", []):
            if fetched >= limit:
                break
            if item.get("object") != "page":
                continue
            result = await _fetch_page_as_text(client, headers, item["id"])
            if result:
                fetched += 1
                yield result

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")


async def _fetch_blocks_text(
    client: httpx.AsyncClient,
    headers: dict,
    block_id: str,
    depth: int = 0,
) -> str:
    if depth > 3:
        return ""  # Don't recurse too deep
    lines: list[str] = []
    cursor: str | None = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        try:
            resp = await client.get(
                f"{_NOTION_BASE}/blocks/{block_id}/children",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        for block in data.get("results", []):
            text = _render_block(block)
            if text:
                lines.append("  " * depth + text)
            if block.get("has_children") and depth < 3:
                child_text = await _fetch_blocks_text(client, headers, block["id"], depth + 1)
                if child_text:
                    lines.append(child_text)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return "\n".join(lines)


def _render_block(block: dict) -> str:
    block_type = block.get("type", "")
    block_data = block.get(block_type, {})
    rich_texts = block_data.get("rich_text", [])
    text = "".join(rt.get("plain_text", "") for rt in rich_texts)

    prefixes = {
        "heading_1": "# ",
        "heading_2": "## ",
        "heading_3": "### ",
        "bulleted_list_item": "- ",
        "numbered_list_item": "1. ",
        "to_do": "- [ ] ",
        "quote": "> ",
        "code": "```\n",
    }
    suffix = "\n```" if block_type == "code" else ""
    prefix = prefixes.get(block_type, "")
    return f"{prefix}{text}{suffix}" if text else ""


def _extract_title(page: dict) -> str:
    props = page.get("properties", {})
    # Notion pages have a title property — could be named anything
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    return page.get("id", "untitled")


def _safe_filename(title: str) -> str:
    import re
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)
    return safe[:128] or "untitled"
