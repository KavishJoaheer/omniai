from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage
from omniai.plugins.llm_providers.openai import ToolCall


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

    async def chat_with_tools(
        self,
        *,
        model: str,
        messages: list[LlmMessage],
        tools: list[dict],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        max_tool_rounds: int = 5,
    ) -> tuple[str, list[ToolCall]]:
        """Non-streaming Anthropic messages API with tool_use support.

        Converts the OpenAI-style ``tools`` list (JSON Schema ``function`` format)
        to Anthropic's ``tools`` format automatically.

        Returns ``(final_text, all_tool_calls_made)`` after the loop completes.
        """
        target_model = model or self._default_model or self.DEFAULT_MODELS[1]
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Convert OpenAI function-calling format → Anthropic tool format
        anthropic_tools: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function", t)  # handle both {type, function: {}} and flat
            anthropic_tools.append({
                "name":        fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })

        system_parts = [m.content for m in messages if m.role == "system"]
        history: list[dict[str, Any]] = [
            {"role": "assistant" if m.role == "assistant" else "user", "content": m.content}
            for m in messages if m.role in ("user", "assistant")
        ]
        all_tool_calls: list[ToolCall] = []

        for _ in range(max_tool_rounds):
            payload: dict[str, Any] = {
                "model":     target_model,
                "messages":  history,
                "max_tokens": max_tokens or 1024,
                "temperature": temperature,
                "tools":     anthropic_tools,
            }
            if system_parts:
                payload["system"] = "\n\n".join(system_parts)

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            stop_reason = data.get("stop_reason", "end_turn")
            content_blocks = data.get("content") or []

            # Collect text blocks
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

            if not tool_use_blocks or stop_reason == "end_turn":
                return "\n".join(text_parts), all_tool_calls

            # Process tool calls — append assistant message then tool results
            history.append({"role": "assistant", "content": content_blocks})
            tool_results: list[dict[str, Any]] = []
            for b in tool_use_blocks:
                tool_call = ToolCall(name=b.get("name", ""), arguments=b.get("input", {}))
                all_tool_calls.append(tool_call)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": b.get("id", ""),
                    "content":     json.dumps({"note": "Tool result pending — implement tool handler."}),
                })
            history.append({"role": "user", "content": tool_results})

        return "", all_tool_calls
