from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage


class OllamaLlmProvider:
    kind = "ollama"

    def __init__(self, *, base_url: str, default_model: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        return [m["name"] for m in data.get("models", [])]

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[LlmMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LlmCompletionChunk]:
        payload: dict = {
            "model": model or self._default_model or "llama3",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line:
                        continue
                    try:
                        record = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    delta = (record.get("message") or {}).get("content", "")
                    done = bool(record.get("done"))
                    finish_reason = "stop" if done else None
                    if delta or done:
                        yield LlmCompletionChunk(delta=delta, finish_reason=finish_reason)
                    if done:
                        break
