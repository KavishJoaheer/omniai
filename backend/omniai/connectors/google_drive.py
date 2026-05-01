"""M17 — Google Drive connector.

Authenticates via a **service account** JSON (recommended for server-to-server
use) or a plain OAuth2 bearer token.  Requires the ``google-api-python-client``
package (``pip install google-api-python-client google-auth``); falls back
gracefully with an ImportError if the package is absent.

Config schema
-------------
{
  "credentials_json": "<service-account JSON string>",   # mutually exclusive
  "access_token":     "<OAuth2 bearer token>",           # with credentials_json
  "folder_id":        "<Drive folder ID>",               # optional; defaults to root
  "shared_drive_id":  "<Shared Drive / Team Drive ID>",  # optional
  "mime_types":       ["application/pdf", "text/plain"], # optional allow-list
  "max_files":        1000                               # optional safety cap
}
"""
from __future__ import annotations

import io
import json
import logging
from collections.abc import AsyncIterator

from omniai.connectors.base import DiscoveredFile, guess_mime

logger = logging.getLogger(__name__)

# Exportable MIME types: Google Workspace formats → plain text / PDF
_EXPORT_MAP: dict[str, str] = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

_DEFAULT_INCLUDE_TYPES = {
    "text/plain",
    "text/csv",
    "text/html",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
}

_MAX_FILES = 1000


class GoogleDriveConnector:
    """Stream files from Google Drive into the ingestion pipeline.

    Config keys:
    - ``credentials_json`` (str): service-account JSON (mutually exclusive with ``access_token``)
    - ``access_token`` (str): OAuth2 bearer token (for user-delegated access)
    - ``folder_id`` (str): folder to sync; omit to sync all accessible files
    - ``shared_drive_id`` (str): Team Drive / Shared Drive ID (optional)
    - ``mime_types`` (list[str]): only these MIME types are returned (optional)
    - ``max_files`` (int): safety cap on number of files (default 1000)
    """

    kind = "google_drive"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        try:
            service = _build_service(config)
        except ImportError as exc:
            logger.error("google_drive connector: google-api-python-client not installed: %s", exc)
            return

        allowed_mime = set(config.get("mime_types") or _DEFAULT_INCLUDE_TYPES)
        folder_id = config.get("folder_id") or "root"
        shared_drive_id = config.get("shared_drive_id")
        max_files = int(config.get("max_files") or _MAX_FILES)

        # Build the files.list query
        query_parts = [f"'{folder_id}' in parents", "trashed = false"]
        query = " and ".join(query_parts)

        extra_kwargs: dict = {}
        if shared_drive_id:
            extra_kwargs.update(
                driveId=shared_drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                corpora="drive",
            )

        seen = 0
        page_token: str | None = None

        while seen < max_files:
            batch_size = min(100, max_files - seen)
            try:
                import asyncio
                result = await asyncio.to_thread(
                    lambda: service.files().list(
                        q=query,
                        pageSize=batch_size,
                        pageToken=page_token,
                        fields="nextPageToken, files(id, name, mimeType, size)",
                        **extra_kwargs,
                    ).execute()
                )
            except Exception as exc:
                logger.error("google_drive: files.list failed: %s", exc)
                break

            for item in result.get("files", []):
                if seen >= max_files:
                    break
                mime = item.get("mimeType", "")
                if mime not in allowed_mime:
                    continue
                file_id = item["id"]
                name = item.get("name", file_id)

                content = await _download_file(service, file_id, mime)
                if content is None:
                    continue

                seen += 1
                yield DiscoveredFile(
                    source_id=f"gdrive:{file_id}",
                    filename=name,
                    mime_type=_export_mime(mime),
                    content=content,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    @staticmethod
    def validate_config(config: dict) -> None:
        has_creds = bool(config.get("credentials_json"))
        has_token = bool(config.get("access_token"))
        if not has_creds and not has_token:
            raise ValueError(
                "google_drive config requires either 'credentials_json' (service account) "
                "or 'access_token' (OAuth2 bearer token)."
            )
        if has_creds and has_token:
            raise ValueError(
                "google_drive config: provide 'credentials_json' OR 'access_token', not both."
            )
        if has_creds:
            creds_raw = config["credentials_json"]
            if isinstance(creds_raw, str):
                try:
                    parsed = json.loads(creds_raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"google_drive: 'credentials_json' is not valid JSON: {exc}"
                    ) from exc
                if parsed.get("type") != "service_account":
                    raise ValueError(
                        "google_drive: 'credentials_json' must be a service account key "
                        "(\"type\": \"service_account\")."
                    )


def _build_service(config: dict):
    """Build a Google Drive API service object from the config."""
    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "google-api-python-client and google-auth are required for the "
            "google_drive connector. Install with: "
            "pip install google-api-python-client google-auth"
        ) from exc

    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    if config.get("credentials_json"):
        info = json.loads(config["credentials_json"]) if isinstance(config["credentials_json"], str) else config["credentials_json"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials(token=config["access_token"])

    return build("drive", "v3", credentials=creds, cache_discovery=False)


async def _download_file(service, file_id: str, mime: str) -> bytes | None:
    import asyncio

    # Google Workspace types must be exported, not downloaded directly
    if mime in _EXPORT_MAP:
        export_mime = _EXPORT_MAP[mime]
        try:
            data = await asyncio.to_thread(
                lambda: service.files().export(fileId=file_id, mimeType=export_mime).execute()
            )
            return data if isinstance(data, bytes) else data.encode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("google_drive: export %s failed: %s", file_id, exc)
            return None

    # Binary download
    try:
        import io
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import-untyped]

        buf = io.BytesIO()
        request = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buf, request)

        done = False
        while not done:
            _, done = await asyncio.to_thread(downloader.next_chunk)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("google_drive: download %s failed: %s", file_id, exc)
        return None


def _export_mime(gdrive_mime: str) -> str:
    return _EXPORT_MAP.get(gdrive_mime, gdrive_mime)
