from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LlmMessage:
    role: str
    content: str


@dataclass(slots=True)
class LlmCompletionChunk:
    delta: str
    finish_reason: str | None = None


class LlmProviderPort(Protocol):
    kind: str

    async def list_models(self) -> list[str]: ...

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[LlmMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LlmCompletionChunk]: ...
