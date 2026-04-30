from __future__ import annotations

from typing import Protocol


class OcrBackend(Protocol):
    """Synchronous OCR backend.

    Takes raw PNG/JPEG bytes of a single rendered page and returns the
    extracted plain text. Implementations are responsible for being safe under
    repeated invocation. They should never raise on transient failures —
    return an empty string and log instead, so the document pipeline keeps
    moving.
    """

    name: str

    def extract(self, image_bytes: bytes) -> str: ...
