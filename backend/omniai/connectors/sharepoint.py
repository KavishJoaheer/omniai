"""M17 — SharePoint / OneDrive connector (Microsoft Graph API).

Authenticates via the **client credentials** OAuth2 flow (app-only); this is
the standard approach for server-to-server integrations.  Requires ``httpx``
(already a transitive dependency) — no additional packages needed.

Config schema
-------------
{
  "tenant_id":    "<Azure AD tenant ID>",
  "client_id":    "<Azure AD app client ID>",
  "client_secret":"<Azure AD app client secret>",
  "site_id":      "<SharePoint site ID or 'root'>",  # optional; default: OneDrive root
  "drive_id":     "<Drive ID>",                       # optional; uses default drive if omitted
  "folder_path":  "/Documents/Reports",               # optional; default: drive root
  "mime_types":   ["application/pdf", "text/plain"],  # optional allow-list
  "max_files":    1000                                # optional safety cap
}
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from omniai.connectors.base import DiscoveredFile, guess_mime

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

_DEFAULT_INCLUDE_EXTS = {
    ".pdf", ".txt", ".md", ".csv", ".docx", ".pptx", ".xlsx", ".html", ".htm"
}
_MAX_FILES = 1000


class SharePointConnector:
    """Stream files from SharePoint / OneDrive via Microsoft Graph.

    Config keys:
    - ``tenant_id``, ``client_id``, ``client_secret``: Azure AD app credentials
    - ``site_id`` (str): SharePoint site ID; omit for the default OneDrive
    - ``drive_id`` (str): specific drive within a site; omit for default drive
    - ``folder_path`` (str): path within the drive (e.g. ``/Documents/Reports``)
    - ``mime_types`` (list[str]): MIME type allow-list (optional)
    - ``max_files`` (int): safety cap (default 1000)
    """

    kind = "sharepoint"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        token = await _get_access_token(config)
        headers = {"Authorization": f"Bearer {token}"}

        drive_root = _build_drive_root(config)
        folder_path = (config.get("folder_path") or "").strip("/")
        if folder_path:
            items_url = f"{drive_root}:/{folder_path}:/children"
        else:
            items_url = f"{drive_root}/root/children"

        allowed_mime = set(config.get("mime_types") or [])
        max_files = int(config.get("max_files") or _MAX_FILES)

        async with httpx.AsyncClient(timeout=30) as client:
            seen = 0
            url: str | None = items_url
            while url and seen < max_files:
                try:
                    resp = await client.get(url, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.error("sharepoint: list failed (%s): %s", url, exc)
                    break

                for item in data.get("value", []):
                    if seen >= max_files:
                        break
                    # Skip folders
                    if "folder" in item:
                        continue
                    name: str = item.get("name", "")
                    file_info = item.get("file", {})
                    mime = file_info.get("mimeType") or guess_mime(name)

                    # Filter by allowed MIME or extension
                    if allowed_mime and mime not in allowed_mime:
                        continue
                    if not allowed_mime:
                        import os
                        if os.path.splitext(name)[1].lower() not in _DEFAULT_INCLUDE_EXTS:
                            continue

                    download_url = item.get("@microsoft.graph.downloadUrl")
                    if not download_url:
                        continue

                    try:
                        dl_resp = await client.get(download_url, timeout=60)
                        dl_resp.raise_for_status()
                        content = dl_resp.content
                    except Exception as exc:
                        logger.warning("sharepoint: download %s failed: %s", name, exc)
                        continue

                    seen += 1
                    yield DiscoveredFile(
                        source_id=f"sharepoint:{item.get('id', name)}",
                        filename=name,
                        mime_type=mime,
                        content=content,
                    )

                # Follow @odata.nextLink for pagination
                url = data.get("@odata.nextLink")

    @staticmethod
    def validate_config(config: dict) -> None:
        for key in ("tenant_id", "client_id", "client_secret"):
            if not config.get(key):
                raise ValueError(f"sharepoint config requires '{key}'.")


async def _get_access_token(config: dict) -> str:
    url = _TOKEN_URL_TMPL.format(tenant_id=config["tenant_id"])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
        })
        resp.raise_for_status()
        return resp.json()["access_token"]


def _build_drive_root(config: dict) -> str:
    site_id = config.get("site_id")
    drive_id = config.get("drive_id")

    if site_id and drive_id:
        return f"{_GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
    if site_id:
        return f"{_GRAPH_BASE}/sites/{site_id}/drive"
    if drive_id:
        return f"{_GRAPH_BASE}/drives/{drive_id}"
    # Default: the authenticated user's OneDrive (app-only → org root)
    return f"{_GRAPH_BASE}/me/drive"
