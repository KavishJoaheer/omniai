from __future__ import annotations

from typing import Protocol


class EmbeddingProviderPort(Protocol):
    kind: str
    dimension: int

    async def embed(self, *, model: str, inputs: list[str]) -> list[list[float]]: ...

    async def list_models(self) -> list[str]: ...
