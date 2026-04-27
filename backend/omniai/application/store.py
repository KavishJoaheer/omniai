"""Backwards-compatible re-export of the knowledge store port.

The canonical definition now lives in `omniai.ports.relational`. This
module is kept so existing imports continue to work.
"""
from __future__ import annotations

from omniai.ports.relational import KnowledgeStorePort as KnowledgeStore

__all__ = ["KnowledgeStore"]
