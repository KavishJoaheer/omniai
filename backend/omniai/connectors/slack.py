"""M17 — Slack connector.

Ingests Slack channel messages via the Slack Web API.  Each channel is
exported as a single plain-text document (most-recent messages first up to
``max_messages_per_channel``).  Only requires ``httpx``.

Config schema
-------------
{
  "bot_token":               "xoxb-...",   # required (Bot User OAuth Token)
  "channel_ids":             ["C01...", "C02..."],  # optional; all joined channels if omitted
  "max_messages_per_channel": 1000,                 # optional safety cap per channel
  "include_threads":          true                  # optional; include threaded replies (default true)
}

Required OAuth scopes: channels:read, channels:history, groups:read,
groups:history (for private), users:read (optional, for display names)
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx

from omniai.connectors.base import DiscoveredFile

logger = logging.getLogger(__name__)

_SLACK_BASE = "https://slack.com/api"
_MAX_MESSAGES = 1000


class SlackConnector:
    """Export Slack channel history into the ingestion pipeline.

    Each channel becomes one ``DiscoveredFile`` with its messages serialised
    as ``[timestamp] <user>: message text`` lines.

    Config keys:
    - ``bot_token`` (str): Slack Bot User OAuth Token (required)
    - ``channel_ids`` (list[str]): IDs of channels to sync (optional; all if omitted)
    - ``max_messages_per_channel`` (int): cap per channel (default 1000)
    - ``include_threads`` (bool): include thread replies (default True)
    """

    kind = "slack"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        token = config["bot_token"]
        max_msgs = int(config.get("max_messages_per_channel") or _MAX_MESSAGES)
        include_threads = bool(config.get("include_threads", True))

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            channel_ids = list(config.get("channel_ids") or [])
            if not channel_ids:
                channel_ids = await _list_channels(client, headers)

            for channel_id in channel_ids:
                df = await _export_channel(
                    client, headers, channel_id, max_msgs, include_threads
                )
                if df:
                    yield df

    @staticmethod
    def validate_config(config: dict) -> None:
        if not config.get("bot_token"):
            raise ValueError("slack config requires 'bot_token'.")
        token = config["bot_token"]
        if not (token.startswith("xoxb-") or token.startswith("xoxp-")):
            raise ValueError(
                "slack config: 'bot_token' must be a Slack Bot Token (xoxb-...) "
                "or User Token (xoxp-...)."
            )


async def _list_channels(client: httpx.AsyncClient, headers: dict) -> list[str]:
    ids: list[str] = []
    cursor: str | None = None

    while True:
        params: dict = {"limit": 200, "types": "public_channel,private_channel"}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = await client.get(f"{_SLACK_BASE}/conversations.list", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("slack: conversations.list failed: %s", exc)
            break

        if not data.get("ok"):
            logger.warning("slack: conversations.list error: %s", data.get("error"))
            break

        for ch in data.get("channels", []):
            if not ch.get("is_archived", False):
                ids.append(ch["id"])

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return ids


async def _export_channel(
    client: httpx.AsyncClient,
    headers: dict,
    channel_id: str,
    max_msgs: int,
    include_threads: bool,
) -> DiscoveredFile | None:
    # Get channel info (name)
    channel_name = channel_id
    try:
        info_resp = await client.get(
            f"{_SLACK_BASE}/conversations.info",
            headers=headers,
            params={"channel": channel_id},
        )
        info_resp.raise_for_status()
        info = info_resp.json()
        if info.get("ok"):
            channel_name = info.get("channel", {}).get("name", channel_id)
    except Exception:
        pass

    # Fetch message history
    lines: list[str] = []
    cursor: str | None = None
    fetched = 0

    while fetched < max_msgs:
        batch = min(200, max_msgs - fetched)
        params: dict = {"channel": channel_id, "limit": batch}
        if cursor:
            params["cursor"] = cursor

        try:
            resp = await client.get(
                f"{_SLACK_BASE}/conversations.history",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("slack: conversations.history %s failed: %s", channel_id, exc)
            break

        if not data.get("ok"):
            logger.warning("slack: conversations.history error: %s", data.get("error"))
            break

        for msg in data.get("messages", []):
            if fetched >= max_msgs:
                break
            ts_float = float(msg.get("ts", 0))
            ts_str = datetime.fromtimestamp(ts_float, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            user = msg.get("user") or msg.get("bot_id") or "unknown"
            text = msg.get("text", "").replace("\n", " ")
            lines.append(f"[{ts_str}] <{user}>: {text}")
            fetched += 1

            # Fetch thread replies
            if include_threads and msg.get("reply_count", 0) > 0:
                thread_lines = await _fetch_thread(client, headers, channel_id, msg["ts"])
                lines.extend(thread_lines)

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    if not lines:
        return None

    header = f"# Slack channel: #{channel_name}\n\n"
    content = (header + "\n".join(lines)).encode("utf-8")
    return DiscoveredFile(
        source_id=f"slack:{channel_id}",
        filename=f"slack_{channel_name}.txt",
        mime_type="text/plain",
        content=content,
    )


async def _fetch_thread(
    client: httpx.AsyncClient,
    headers: dict,
    channel_id: str,
    thread_ts: str,
) -> list[str]:
    lines: list[str] = []
    try:
        resp = await client.get(
            f"{_SLACK_BASE}/conversations.replies",
            headers=headers,
            params={"channel": channel_id, "ts": thread_ts, "limit": 50},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return lines

    if not data.get("ok"):
        return lines

    for msg in data.get("messages", [])[1:]:  # skip the parent message (already included)
        ts_float = float(msg.get("ts", 0))
        ts_str = datetime.fromtimestamp(ts_float, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        user = msg.get("user") or msg.get("bot_id") or "unknown"
        text = msg.get("text", "").replace("\n", " ")
        lines.append(f"  └ [{ts_str}] <{user}>: {text}")

    return lines
