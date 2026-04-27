from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage


class GeminiLlmProvider:
    kind = "gemini"

    DEFAULT_MODELS = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]

    def __init__(self, *, api_key: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta", default_model: str | None = None) -> None:
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
        chosen_model = model or self._default_model or self.DEFAULT_MODELS[0]
        contents = []
        system_text: list[str] = []
        for m in messages:
            if m.role == "system":
                system_text.append(m.content)
            else:
                contents.append({
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                })

        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_text)}]}

        url = f"{self._base_url}/models/{chosen_model}:streamGenerateContent?alt=sse&key={self._api_key}"
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    body = raw_line[len("data:"):].strip()
                    if not body:
                        continue
                    try:
                        event = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    candidates = event.get("candidates") or []
                    for candidate in candidates:
                        parts = (candidate.get("content") or {}).get("parts") or []
                        for part in parts:
                            text = part.get("text") or ""
                            if text:
                                yield LlmCompletionChunk(delta=text)
                        if candidate.get("finishReason"):
                            yield LlmCompletionChunk(delta="", finish_reason="stop")
                            return
