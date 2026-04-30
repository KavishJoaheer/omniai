"""Best-effort token counting for LLM usage tracking.

Strategy (in order of preference):
1. ``tiktoken`` — exact BPE tokenisation for OpenAI / Anthropic models.
   Optional dep; installed via  pip install tiktoken
2. Character-ratio fallback — ~4 chars per token is a well-known heuristic
   that's accurate to ±15 % for English text, good enough for billing estimates.

All public functions return ``int`` and never raise.
"""
from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")

# ── tiktoken (optional) ────────────────────────────────────────────────────

try:
    import tiktoken as _tiktoken

    def _get_encoding(model: str):
        try:
            return _tiktoken.encoding_for_model(model)
        except KeyError:
            # Unknown model — fall back to cl100k_base (GPT-4 / Claude-compatible)
            return _tiktoken.get_encoding("cl100k_base")

    def _tiktoken_count(text: str, model: str) -> int:
        enc = _get_encoding(model)
        return len(enc.encode(text, disallowed_special=()))

    _TIKTOKEN_AVAILABLE = True

except ImportError:
    _TIKTOKEN_AVAILABLE = False

    def _tiktoken_count(text: str, model: str) -> int:  # type: ignore[misc]
        raise NotImplementedError


# ── character-ratio fallback ───────────────────────────────────────────────

def _char_ratio_count(text: str) -> int:
    """~4 characters per token heuristic.  Rounds up."""
    return max(1, (len(text) + 3) // 4)


# ── public API ─────────────────────────────────────────────────────────────

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Return the approximate token count for *text* with respect to *model*.

    Uses tiktoken if available, otherwise falls back to the character-ratio
    heuristic.  The result is suitable for usage tracking and quota enforcement;
    it is NOT suitable for computing exact prompt-size constraints.
    """
    if not text:
        return 0
    if _TIKTOKEN_AVAILABLE:
        try:
            return _tiktoken_count(text, model)
        except Exception:
            pass
    return _char_ratio_count(text)


def estimate_usage(prompt: str, completion: str, model: str = "gpt-4") -> dict[str, int]:
    """Return a ``{prompt_tokens, completion_tokens, total_tokens}`` dict."""
    pt = count_tokens(prompt, model)
    ct = count_tokens(completion, model)
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
    }
