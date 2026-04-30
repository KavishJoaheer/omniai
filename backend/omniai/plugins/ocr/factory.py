from __future__ import annotations

import logging

from omniai.config.settings import Settings
from omniai.plugins.ocr.base import OcrBackend

logger = logging.getLogger(__name__)


def build_ocr_backend(settings: Settings) -> OcrBackend | None:
    """Resolve an OCR backend or return None to disable OCR.

    Resolution order driven by settings.ocr_kind:
      - "none" / "" / unset → return None
      - "tesseract"          → load TesseractOcrBackend; warn + return None on import failure
      - "ollama_vision"      → load OllamaVisionOcrBackend (no probe — failures
                                surface lazily and are caught inside extract())
      - any other            → warn + return None
    """
    kind = (settings.ocr_kind or "").lower().strip()
    if kind in ("", "none"):
        return None

    if kind == "tesseract":
        try:
            from omniai.plugins.ocr.tesseract import TesseractOcrBackend
            return TesseractOcrBackend()
        except ImportError as exc:
            logger.warning("ocr: tesseract requested but unavailable: %s", exc)
            return None

    if kind in ("ollama_vision", "ollama"):
        from omniai.plugins.ocr.ollama_vision import OllamaVisionOcrBackend

        return OllamaVisionOcrBackend(
            base_url=settings.ollama_base_url,
            model=settings.ollama_vision_model,
        )

    logger.warning("ocr: unknown OCR_KIND=%r, OCR disabled", kind)
    return None
