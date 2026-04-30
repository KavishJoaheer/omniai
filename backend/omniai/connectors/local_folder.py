from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

from omniai.connectors.base import DiscoveredFile, guess_mime

logger = logging.getLogger(__name__)

_DEFAULT_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx", ".html", ".htm"}
_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB safety cap per file


class LocalFolderConnector:
    """Recursively walks a local directory, yielding supported files.

    Config schema:
        {
          "path": "/abs/path/to/watch",
          "extensions": [".pdf", ".md"],   # optional, defaults to common docs
          "max_bytes_per_file": 52428800,  # optional override
          "recursive": true                # default true
        }
    """

    kind = "local_folder"

    async def discover(self, config: dict) -> AsyncIterator[DiscoveredFile]:
        path = config.get("path")
        if not path:
            return
        root = Path(path).expanduser()
        if not root.exists() or not root.is_dir():
            logger.warning("local_folder connector: path does not exist or is not a dir: %s", root)
            return

        allowed_exts = {e.lower() for e in (config.get("extensions") or _DEFAULT_EXTENSIONS)}
        max_bytes = int(config.get("max_bytes_per_file") or _MAX_BYTES)
        recursive = bool(config.get("recursive", True))
        iterator = root.rglob("*") if recursive else root.iterdir()

        for path_obj in iterator:
            try:
                if not path_obj.is_file():
                    continue
                if path_obj.suffix.lower() not in allowed_exts:
                    continue
                size = path_obj.stat().st_size
                if size == 0 or size > max_bytes:
                    continue
                # Read off the asyncio loop — file I/O can block
                content = await asyncio.to_thread(path_obj.read_bytes)
            except OSError as exc:
                logger.warning("local_folder: cannot read %s: %s", path_obj, exc)
                continue

            yield DiscoveredFile(
                source_id=str(path_obj.resolve()),
                filename=path_obj.name,
                mime_type=guess_mime(path_obj.name),
                content=content,
            )

    @staticmethod
    def validate_config(config: dict) -> None:
        path = config.get("path")
        if not path or not isinstance(path, str):
            raise ValueError("local_folder config requires 'path' (string).")
        # Allow non-existent paths at registration time — they may appear later
        # when a folder is mounted. We just resolve to absolute for safety.
        os.fspath(Path(path).expanduser())
