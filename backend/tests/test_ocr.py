"""OCR fallback tests.

We don't synthesize real scanned PDFs here — that requires reportlab + a font
and a real PIL image. Instead we exercise:
  1. The OCR factory's resolution logic
  2. PdfParser's decision to invoke OCR (via a fake backend that records calls)
  3. OllamaVisionOcrBackend's HTTP call shape (httpx mock)

This keeps tests fast and deterministic while still covering the contract.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---- factory ----------------------------------------------------------------

class _StubSettings:
    """Minimal duck-typed Settings for the factory."""

    def __init__(self, kind: str, *, ollama_base_url: str = "http://localhost:11434", model: str = "llava"):
        self.ocr_kind = kind
        self.ollama_base_url = ollama_base_url
        self.ollama_vision_model = model


def test_factory_returns_none_when_disabled():
    from omniai.plugins.ocr.factory import build_ocr_backend

    assert build_ocr_backend(_StubSettings("none")) is None
    assert build_ocr_backend(_StubSettings("")) is None


def test_factory_returns_ollama_backend():
    from omniai.plugins.ocr.factory import build_ocr_backend
    from omniai.plugins.ocr.ollama_vision import OllamaVisionOcrBackend

    backend = build_ocr_backend(_StubSettings("ollama_vision"))
    assert isinstance(backend, OllamaVisionOcrBackend)


def test_factory_unknown_kind_returns_none():
    from omniai.plugins.ocr.factory import build_ocr_backend

    assert build_ocr_backend(_StubSettings("does-not-exist")) is None


def test_factory_tesseract_falls_back_when_unavailable():
    """If pytesseract or the binary isn't installed the factory should not
    crash; it must return None and let the caller proceed."""
    from omniai.plugins.ocr.factory import build_ocr_backend

    # Force the import to fail by patching __import__ for pytesseract.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pytesseract":
            raise ImportError("simulated missing")
        return real_import(name, *args, **kwargs)

    if isinstance(__builtins__, dict):
        with patch.dict(__builtins__, {"__import__": fake_import}):
            assert build_ocr_backend(_StubSettings("tesseract")) is None
    else:
        with patch("builtins.__import__", side_effect=fake_import):
            assert build_ocr_backend(_StubSettings("tesseract")) is None


# ---- PdfParser integration with a fake backend -----------------------------

class _RecordingOcr:
    name = "fake"

    def __init__(self, return_text: str = "OCR-RECOVERED-TEXT"):
        self.calls: list[bytes] = []
        self._return = return_text

    def extract(self, image_bytes: bytes) -> str:
        self.calls.append(image_bytes)
        return self._return


def _build_text_pdf_with_two_pages() -> bytes:
    """Generate a tiny 2-page PDF where both pages have abundant native text.

    Used to assert OCR is NOT invoked when the threshold is satisfied.
    Skips the test if reportlab is not available.
    """
    reportlab = pytest.importorskip("reportlab")
    from io import BytesIO
    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    c = Canvas(buf)
    for page_text in (
        "This is page one with plenty of meaningful native text content " * 5,
        "This is page two also bearing rich native text we can extract " * 5,
    ):
        c.drawString(72, 720, page_text)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_parser_skips_ocr_when_text_is_plentiful():
    pdf_bytes = _build_text_pdf_with_two_pages()
    from omniai.plugins.parsers.pdf import PdfParser

    spy = _RecordingOcr()
    parser = PdfParser(ocr_backend=spy, ocr_min_chars_per_page=20)
    result = parser.parse(data=pdf_bytes, filename="textual.pdf")

    assert result.page_count == 2
    assert "page one" in result.text
    assert "page two" in result.text
    assert spy.calls == [], "OCR should not run on text-rich pages"
    assert result.metadata.get("extractor") == "pdfplumber"
    assert result.metadata.get("ocr_pages") == 0


def test_pdf_parser_invokes_ocr_when_text_is_sparse():
    """A page with <ocr_min_chars characters should trigger OCR."""
    pytest.importorskip("reportlab")
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    c = Canvas(buf)
    # Single sparse page — only 3 chars of native text
    c.drawString(72, 720, "Hi")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    from omniai.plugins.parsers.pdf import PdfParser

    spy = _RecordingOcr(return_text="recovered scanned content")
    parser = PdfParser(ocr_backend=spy, ocr_min_chars_per_page=50)
    result = parser.parse(data=pdf_bytes, filename="scanned.pdf")

    assert len(spy.calls) == 1, "OCR backend should have been called once"
    assert "recovered scanned content" in result.text
    assert result.metadata.get("extractor") == "pdfplumber+ocr"
    assert result.metadata.get("ocr_pages") == 1


# ---- OllamaVisionOcrBackend HTTP wire format -------------------------------

def test_ollama_vision_backend_sends_expected_payload():
    """The Ollama vision backend should base64-encode the image and POST to
    /api/generate with the right shape."""
    import base64
    import httpx

    from omniai.plugins.ocr.ollama_vision import OllamaVisionOcrBackend

    captured = {}

    def fake_post(self, url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"response": "transcribed text"},
        )

    backend = OllamaVisionOcrBackend(base_url="http://localhost:11434", model="llava")

    with patch.object(httpx.Client, "post", new=fake_post):
        text = backend.extract(b"\x89PNG\r\n")

    assert text == "transcribed text"
    assert captured["url"] == "http://localhost:11434/api/generate"
    body = captured["json"]
    assert body["model"] == "llava"
    assert body["stream"] is False
    assert body["images"] == [base64.b64encode(b"\x89PNG\r\n").decode("ascii")]


def test_ollama_vision_backend_swallows_errors():
    """A failing HTTP call must NOT raise — return empty string so the
    document pipeline can move on."""
    import httpx

    from omniai.plugins.ocr.ollama_vision import OllamaVisionOcrBackend

    def fake_post(self, url, json=None, **kwargs):
        raise httpx.ConnectError("simulated connection failure")

    backend = OllamaVisionOcrBackend(base_url="http://localhost:11434")
    with patch.object(httpx.Client, "post", new=fake_post):
        assert backend.extract(b"\x89PNG\r\n") == ""
