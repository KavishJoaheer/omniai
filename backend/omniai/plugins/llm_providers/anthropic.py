from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage


class AnthropicLlmProvider:
    kind = "anthropic"

    DEFAULT_MODELS = [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]

    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com", default_model: str | None = None) -> None:
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
        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload = {
            "model": model or self._default_model or self.DEFAULT_MODELS[1],
            "messages": chat_messages,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
            "stream": True,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/messages",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    body = raw_line[len("data:"):].strip()
                    if not body or body == "[DONE]":
                        continue
                    try:
                        event = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type == "content_block_delta":
                        delta = (event.get("delta") or {}).get("text", "")
                        if delta:
                            yield LlmCompletionChunk(delta=delta)
                    elif event_type == "message_stop":
                        yield LlmCompletionChunk(delta="", finish_reason="stop")
                        break
