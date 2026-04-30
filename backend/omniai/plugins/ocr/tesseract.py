from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


class TesseractOcrBackend:
    """Local OCR via the Tesseract engine.

    Requires the system `tesseract` binary AND the `pytesseract` + `Pillow`
    Python packages. The constructor probes for both — raises ImportError if
    either is missing. The factory falls back to a no-op when this happens.
    """

    name = "tesseract"

    def __init__(self) -> None:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "tesseract OCR requires `pytesseract` and `Pillow`. "
                "Install with: pip install pytesseract pillow, plus the system tesseract binary."
            ) from exc
        self._pytesseract = pytesseract
        self._Image = Image
        # Probe the binary; if not present, surface the failure now (not on first use)
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:  # pragma: no cover
            raise ImportError(
                "tesseract OCR: the `tesseract` binary was not found on PATH. "
                "Install it via your package manager (e.g. `apt install tesseract-ocr`)."
            ) from exc

    def extract(self, image_bytes: bytes) -> str:
        try:
            image = self._Image.open(io.BytesIO(image_bytes))
            text = self._pytesseract.image_to_string(image)
            return (text or "").strip()
        except Exception:
            logger.exception("tesseract OCR failed")
            return ""
