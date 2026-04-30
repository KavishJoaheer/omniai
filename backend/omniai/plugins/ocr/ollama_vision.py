from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

_PROMPT = (
    "Transcribe ALL the text visible in this page image, preserving paragraph "
    "structure. Output ONLY the transcribed text with no commentary, no "
    "preamble, and no markdown fences."
)


class OllamaVisionOcrBackend:
    """OCR via an Ollama-hosted vision model (e.g. llava, llama3.2-vision).

    Sends the page image as a base64 string to /api/generate with the chosen
    model. Synchronous (uses httpx.Client) so it can be called from the parser
    without restructuring the call site as async.
    """

    name = "ollama_vision"

    def __init__(self, *, base_url: str, model: str = "llava", timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def extract(self, image_bytes: bytes) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self._model,
            "prompt": _PROMPT,
            "images": [encoded],
            "stream": False,
            "options": {"temperature": 0.0},
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("ollama_vision OCR failed")
            return ""
        text = data.get("response") or ""
        return text.strip()
