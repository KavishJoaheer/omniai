from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage


class OpenAILlmProvider:
    kind = "openai"

    DEFAULT_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    def __init__(self, *, api_key: str, base_url: str = "https://api.openai.com/v1", default_model: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def list_models(self) -> list[str]:
        return list(self.DEFAULT_MODELS)

    async def stream_chat(
        self,
        *,
        model: str,
        messages: list[LlmMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LlmCompletionChunk]:
        payload = {
            "model": model or self._default_model or self.DEFAULT_MODELS[0],
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    body = raw_line[len("data:"):].strip()
                    if not body or body == "[DONE]":
                        if body == "[DONE]":
                            yield LlmCompletionChunk(delta="", finish_reason="stop")
                        continue
                    try:
                        event = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = (choice.get("delta") or {}).get("content", "")
                    finish = choice.get("finish_reason")
                    if delta or finish:
                        yield LlmCompletionChunk(delta=delta or "", finish_reason=finish)
