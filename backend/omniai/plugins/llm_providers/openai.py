from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from omniai.ports.llm_provider import LlmCompletionChunk, LlmMessage


@dataclass
class ToolCall:
    """Represents a function/tool call returned by the model."""
    name: str
    arguments: dict


@dataclass
class ToolCallResult:
    """Text result to inject back as a tool response."""
    tool_call_id: str
    name: str
    content: str


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
        """Non-streaming chat with OpenAI function/tool calling.

        Runs an agentic loop:
          1. Send messages + tool definitions to the model.
          2. If the model invokes a tool, yield the ToolCall; caller must supply
             the result via the returned list.  (Currently processes one round
             internally — callers that want multi-round should call repeatedly.)
          3. When the model emits a final text response, return it.

        Returns ``(final_text, all_tool_calls_made)`` after the loop completes.
        """
        target_model = model or self._default_model or self.DEFAULT_MODELS[0]
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        history: list[dict] = [{"role": m.role, "content": m.content} for m in messages]
        all_tool_calls: list[ToolCall] = []

        for _ in range(max_tool_rounds):
            payload: dict[str, Any] = {
                "model": target_model,
                "messages": history,
                "temperature": temperature,
                "tools": tools,
                "tool_choice": "auto",
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            choice = (data.get("choices") or [{}])[0]
            finish_reason = choice.get("finish_reason", "stop")
            msg = choice.get("message", {})
            raw_tool_calls = msg.get("tool_calls") or []

            if not raw_tool_calls or finish_reason == "stop":
                return msg.get("content") or "", all_tool_calls

            # Process tool calls
            history.append(msg)  # assistant message with tool_calls
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                tool_call = ToolCall(name=fn.get("name", ""), arguments=args)
                all_tool_calls.append(tool_call)
                # Append a placeholder tool result — callers should override this
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps({"note": "Tool result pending — implement tool handler."}),
                })

        return "", all_tool_calls
