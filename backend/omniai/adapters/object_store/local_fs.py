from __future__ import annotations

from pathlib import Path
from typing import BinaryIO


class LocalFsObjectStore:
    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put_object(self, *, key: str, data: BinaryIO, content_type: str, size: int) -> str:
        target = self._safe_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            while True:
                chunk = data.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
        return f"local://{key}"

    def get_object(self, *, key: str) -> bytes:
        target = self._safe_path(key)
        if not target.exists():
            raise FileNotFoundError(key)
        return target.read_bytes()

    def delete_object(self, *, key: str) -> None:
        target = self._safe_path(key)
        if target.exists():
            target.unlink()

    def presigned_get_url(self, *, key: str, expires_seconds: int = 3600) -> str:
        return f"file://{self._safe_path(key)}"

    def _safe_path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise ValueError(f"Refusing to write outside storage root: {key}")
        return candidate
