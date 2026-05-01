"""M20 — Agent Template Marketplace.

Provides a curated set of built-in agent templates and an import-from-URL
mechanism so teams can share and reuse agent definitions.

Built-in templates
------------------
Templates are versioned dictionaries embedded in this module (no network
required).  External registries can be fetched via ``import_from_url()``.

Template schema
---------------
Each template is a dict with the following top-level keys:

  id          : str   — stable, kebab-cased identifier
  name        : str   — human-readable display name
  description : str   — what the agent does
  category    : str   — grouping label (e.g. "research", "support")
  definition  : dict  — the full agent ``definition`` object (nodes + edges)
  tags        : list  — free-form tags for filtering
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Built-in templates ────────────────────────────────────────────────────────

_BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "basic-rag",
        "name": "Basic RAG",
        "description": "Retrieval-augmented generation: search the knowledge base then generate a grounded answer.",
        "category": "research",
        "tags": ["rag", "retrieval", "qa"],
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",     "type": "start",     "label": "Start"},
                {"id": "retrieval", "type": "retrieval",  "label": "Retrieve"},
                {"id": "generate",  "type": "generate",   "label": "Generate"},
                {"id": "end",       "type": "end",        "label": "End"},
            ],
            "edges": [
                {"from": "start",     "to": "retrieval"},
                {"from": "retrieval", "to": "generate"},
                {"from": "generate",  "to": "end"},
            ],
            "collectionIds": [],
            "retrieval": {"topK": 5, "vectorWeight": 0.65},
            "generation": {
                "mode": "local-grounded",
                "fallbackText": "I could not find a grounded answer in the knowledge base.",
            },
        },
    },
    {
        "id": "parallel-research",
        "name": "Parallel Research",
        "description": "Fan-out into multiple knowledge bases simultaneously, then join results for a richer answer.",
        "category": "research",
        "tags": ["rag", "parallel", "fan-out"],
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",     "type": "start",    "label": "Start"},
                {"id": "fan_out",   "type": "fan_out",  "label": "Fan Out",
                 "config": {"branches": ["retrieval_a", "retrieval_b"]}},
                {"id": "retrieval_a", "type": "retrieval", "label": "Retrieve A",
                 "config": {"topK": 4, "vectorWeight": 0.7}},
                {"id": "retrieval_b", "type": "retrieval", "label": "Retrieve B",
                 "config": {"topK": 4, "vectorWeight": 0.5}},
                {"id": "join",      "type": "join",     "label": "Join"},
                {"id": "generate",  "type": "generate", "label": "Generate"},
                {"id": "end",       "type": "end",      "label": "End"},
            ],
            "edges": [
                {"from": "start",       "to": "fan_out"},
                {"from": "fan_out",     "to": "retrieval_a"},
                {"from": "fan_out",     "to": "retrieval_b"},
                {"from": "retrieval_a", "to": "join"},
                {"from": "retrieval_b", "to": "join"},
                {"from": "join",        "to": "generate"},
                {"from": "generate",    "to": "end"},
            ],
            "collectionIds": [],
            "retrieval": {"topK": 4, "vectorWeight": 0.65},
            "generation": {"mode": "local-grounded",
                           "fallbackText": "No relevant context found."},
        },
    },
    {
        "id": "human-review",
        "name": "Human-in-the-Loop Review",
        "description": "Retrieve context and pause for human review before generating the final answer.",
        "category": "support",
        "tags": ["hitl", "review", "approval"],
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",       "type": "start",       "label": "Start"},
                {"id": "retrieval",   "type": "retrieval",   "label": "Retrieve"},
                {"id": "human_input", "type": "human_input", "label": "Human Review",
                 "config": {"prompt": "Please review the retrieved context and approve or edit before we generate the answer."}},
                {"id": "generate",    "type": "generate",    "label": "Generate"},
                {"id": "end",         "type": "end",         "label": "End"},
            ],
            "edges": [
                {"from": "start",       "to": "retrieval"},
                {"from": "retrieval",   "to": "human_input"},
                {"from": "human_input", "to": "generate"},
                {"from": "generate",    "to": "end"},
            ],
            "collectionIds": [],
            "retrieval": {"topK": 5, "vectorWeight": 0.65},
            "generation": {"mode": "local-grounded",
                           "fallbackText": "No relevant context found."},
        },
    },
    {
        "id": "code-executor",
        "name": "Code Executor",
        "description": "Retrieve relevant context then execute a Python snippet to compute a result.",
        "category": "automation",
        "tags": ["code", "python", "automation"],
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",     "type": "start",     "label": "Start"},
                {"id": "retrieval", "type": "retrieval",  "label": "Retrieve"},
                {"id": "code",      "type": "code",       "label": "Compute",
                 "config": {"language": "python",
                             "code": "print(f'Context has {len(context_text)} chars.')",
                             "timeout_seconds": 10}},
                {"id": "end",       "type": "end",        "label": "End"},
            ],
            "edges": [
                {"from": "start",     "to": "retrieval"},
                {"from": "retrieval", "to": "code"},
                {"from": "code",      "to": "end"},
            ],
            "collectionIds": [],
            "retrieval": {"topK": 3, "vectorWeight": 0.7},
            "generation": {"mode": "local-grounded",
                           "fallbackText": "No relevant context found."},
        },
    },
    {
        "id": "summarisation",
        "name": "Document Summarisation",
        "description": "Retrieve the most relevant passages and produce a concise summary.",
        "category": "content",
        "tags": ["summary", "content", "writing"],
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",     "type": "start",    "label": "Start"},
                {"id": "retrieval", "type": "retrieval", "label": "Retrieve",
                 "config": {"topK": 10, "vectorWeight": 0.6}},
                {"id": "generate",  "type": "generate",  "label": "Summarise"},
                {"id": "message",   "type": "message",   "label": "Format",
                 "config": {"template": "Summary:\n\n{answer}"}},
                {"id": "end",       "type": "end",       "label": "End"},
            ],
            "edges": [
                {"from": "start",     "to": "retrieval"},
                {"from": "retrieval", "to": "generate"},
                {"from": "generate",  "to": "message"},
                {"from": "message",   "to": "end"},
            ],
            "collectionIds": [],
            "retrieval": {"topK": 10, "vectorWeight": 0.6},
            "generation": {"mode": "local-grounded",
                           "fallbackText": "No content to summarise."},
        },
    },
]

_TEMPLATES_BY_ID: dict[str, dict] = {t["id"]: t for t in _BUILTIN_TEMPLATES}


# ── Service ───────────────────────────────────────────────────────────────────

@dataclass
class MarketplaceService:
    """Read-only view over built-in templates + optional HTTP fetch for external ones."""

    _http_timeout: float = field(default=10.0)

    def list_templates(self, *, category: str | None = None, tag: str | None = None) -> list[dict]:
        """Return all built-in templates, optionally filtered."""
        templates = list(_BUILTIN_TEMPLATES)
        if category:
            templates = [t for t in templates if t.get("category") == category]
        if tag:
            templates = [t for t in templates if tag in (t.get("tags") or [])]
        # Return without the full definition to keep the listing lean
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t["description"],
                "category": t.get("category", ""),
                "tags": t.get("tags", []),
            }
            for t in templates
        ]

    def get_template(self, template_id: str) -> dict:
        """Return the full template (including definition) by ID.

        Raises ``KeyError`` if not found.
        """
        if template_id not in _TEMPLATES_BY_ID:
            raise KeyError(f"Template not found: {template_id!r}")
        return dict(_TEMPLATES_BY_ID[template_id])

    async def import_from_url(self, url: str) -> dict:
        """Fetch an agent template definition from a remote URL.

        The URL must return a JSON object conforming to the template schema
        (at minimum: ``name`` and ``definition``).

        Raises ``ValueError`` if the response is not valid JSON or missing
        required fields.
        Raises ``RuntimeError`` on HTTP/network errors.
        """
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for URL imports: pip install httpx") from exc

        try:
            async with httpx.AsyncClient(timeout=self._http_timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"HTTP {exc.response.status_code} fetching template from {url}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch template from {url}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Template URL must return a JSON object, got {type(data).__name__}")
        if "definition" not in data:
            raise ValueError("Template JSON must contain a 'definition' field")
        if "name" not in data:
            raise ValueError("Template JSON must contain a 'name' field")

        # Ensure required definition sub-fields exist
        defn = data["definition"]
        if not isinstance(defn, dict):
            raise ValueError("Template 'definition' must be a JSON object")

        logger.info("marketplace: imported template %r from %s", data.get("name"), url)
        return data
