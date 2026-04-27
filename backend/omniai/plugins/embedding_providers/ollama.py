from __future__ import annotations

import httpx


class OllamaEmbeddingProvider:
    kind = "embedding"
    name = "ollama"

    def __init__(self, *, base_url: str, default_model: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    @property
    def dimension(self) -> int:
        return 0

    async def embed(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        chosen_model = model or self._default_model
        if not chosen_model:
            raise ValueError("Ollama embedding requires a model name.")
        async with httpx.AsyncClient(timeout=60.0) as client:
            results: list[list[float]] = []
            for text in inputs:
                response = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": chosen_model, "prompt": text},
                )
                response.raise_for_status()
                payload = response.json()
                vector = payload.get("embedding")
                if not isinstance(vector, list):
                    raise RuntimeError(f"Ollama returned no embedding for model {chosen_model!r}")
                results.append([float(v) for v in vector])
        return results

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self._base_url}/api/tags")
                response.raise_for_status()
            except httpx.HTTPError:
                return []
        names: list[str] = []
        for entry in response.json().get("models") or []:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str):
                names.append(name)
        return names
