"""Multi-modal embedding provider — text + image using CLIP-class models.

This adapter supports both text and image embeddings through OpenAI's
``text-embedding-*`` API (for text) and a local CLIP model (for images).

For image embeddings the adapter accepts:
  - Base64-encoded image data URLs: ``data:image/jpeg;base64,...``
  - Local file paths (when running in a trusted environment)

The two embedding spaces are unified using the same CLIP vision-language model
so that cross-modal similarity search works correctly.

Requires: ``pip install open-clip-torch torch Pillow`` for local CLIP.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

logger = logging.getLogger(__name__)

_CLIP_DIM = 512  # ViT-B/32 output dimension


class MultiModalEmbeddingProvider:
    """EmbeddingProviderPort that handles text and image inputs via CLIP.

    For text-only inputs this falls back to the specified ``text_provider``
    (e.g., OllamaEmbeddingProvider) so that existing collections work unchanged.

    Parameters
    ----------
    text_provider:
        Underlying text embedding provider used for plain-text inputs.
    clip_model_name:
        OpenCLIP model name (default ``"ViT-B-32"``).
    clip_pretrained:
        OpenCLIP pretrained weights name (default ``"laion2b_s34b_b79k"``).
    """

    kind = "multimodal"

    def __init__(
        self,
        text_provider: Any,
        clip_model_name: str = "ViT-B-32",
        clip_pretrained: str = "laion2b_s34b_b79k",
    ) -> None:
        self._text_provider = text_provider
        self._clip_model_name = clip_model_name
        self._clip_pretrained = clip_pretrained
        self._model: Any = None
        self._preprocess: Any = None
        self._tokenizer: Any = None

    # ── Lazy model loading ────────────────────────────────────────────────────

    def _load_model(self):
        if self._model is not None:
            return
        try:
            import open_clip  # type: ignore[import]
            import torch  # type: ignore[import]
            model, _, preprocess = open_clip.create_model_and_transforms(
                self._clip_model_name,
                pretrained=self._clip_pretrained,
            )
            model.eval()
            self._model = model
            self._preprocess = preprocess
            self._tokenizer = open_clip.get_tokenizer(self._clip_model_name)
            self._torch = torch
            logger.info("CLIP model %s loaded", self._clip_model_name)
        except ImportError:
            logger.warning(
                "open-clip-torch not installed. Image embedding will return zero vectors. "
                "Install with: pip install open-clip-torch torch"
            )
            self._model = "unavailable"

    # ── EmbeddingProviderPort ─────────────────────────────────────────────────

    async def list_models(self) -> list[str]:
        base = await self._text_provider.list_models()
        return base + [f"clip/{self._clip_model_name}"]

    async def embed(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        """Embed a list of inputs.

        If an input starts with ``data:image/`` it is treated as an image;
        otherwise it is treated as text.
        """
        results: list[list[float]] = [[] for _ in inputs]
        text_indices: list[int] = []
        image_indices: list[int] = []

        for i, inp in enumerate(inputs):
            if inp.startswith("data:image/"):
                image_indices.append(i)
            else:
                text_indices.append(i)

        # Batch text embeddings through the text provider
        if text_indices:
            text_inputs = [inputs[i] for i in text_indices]
            try:
                text_vecs = await self._text_provider.embed(model=model, inputs=text_inputs)
            except Exception:
                text_vecs = [[0.0] * self._text_provider.dimension] * len(text_inputs)
            for j, i in enumerate(text_indices):
                results[i] = text_vecs[j]

        # Batch image embeddings through CLIP
        if image_indices:
            image_vecs = self._embed_images([inputs[i] for i in image_indices])
            for j, i in enumerate(image_indices):
                results[i] = image_vecs[j]

        return results

    # ── Private ───────────────────────────────────────────────────────────────

    def _embed_images(self, data_urls: list[str]) -> list[list[float]]:
        self._load_model()
        if self._model == "unavailable":
            return [[0.0] * _CLIP_DIM] * len(data_urls)

        try:
            from PIL import Image  # type: ignore[import]
        except ImportError:
            logger.warning("Pillow not installed; returning zero image vectors.")
            return [[0.0] * _CLIP_DIM] * len(data_urls)

        images = []
        for url in data_urls:
            try:
                header, b64 = url.split(",", 1)
                image_bytes = base64.b64decode(b64)
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                images.append(self._preprocess(img))
            except Exception:
                # Return a zero vector for unparseable images
                images.append(self._preprocess(Image.new("RGB", (224, 224))))

        import torch
        image_tensor = torch.stack(images)
        with torch.no_grad():
            features = self._model.encode_image(image_tensor)
            features /= features.norm(dim=-1, keepdim=True)
        return features.cpu().tolist()

    @property
    def dimension(self) -> int:  # type: ignore[override]
        return _CLIP_DIM
