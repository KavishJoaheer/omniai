"""M16 — Observability & Cost service.

Provides:
  1. Token usage recording + per-tenant cost aggregation
  2. Retrieval quality feedback (thumbs up/down) + NDCG calculation
"""
from __future__ import annotations

import hashlib
import json
import math
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    RetrievalFeedbackRecord,
    TokenUsageRecord,
    generate_prefixed_id,
)
from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.config.settings import Settings
from omniai.domain.knowledge.models import utc_now
from omniai.security.permissions import Perm, assert_permission

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class RetrievalFeedbackInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    chunk_id: str = Field(min_length=1)
    rank: int = Field(ge=1, le=100, description="1-based position in the result list")
    relevant: bool = Field(description="True = relevant, False = not relevant")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ObservabilityService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ── Token usage ──────────────────────────────────────────────────────────

    def record_token_usage(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        conversation_id: str | None,
        model_provider: str | None,
        model_name: str | None,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Persist one LLM call's token usage.  Fire-and-forget — never raises."""
        try:
            record = TokenUsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                model_provider=model_provider,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            self._session.add(record)
            self._session.commit()
        except Exception:
            logger.exception("Failed to record token usage")
            try:
                self._session.rollback()
            except Exception:
                pass

    def get_cost_dashboard(
        self,
        principal: AuthenticatedPrincipal,
        *,
        days: int = 30,
    ) -> dict:
        """Return aggregated token usage + estimated cost for the principal's tenant."""
        assert_permission(principal.role, Perm.AUDIT_READ)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        rows = list(self._session.execute(
            select(
                TokenUsageRecord.model_provider,
                TokenUsageRecord.model_name,
                func.sum(TokenUsageRecord.prompt_tokens).label("prompt_tokens"),
                func.sum(TokenUsageRecord.completion_tokens).label("completion_tokens"),
                func.sum(TokenUsageRecord.total_tokens).label("total_tokens"),
                func.count(TokenUsageRecord.id).label("calls"),
            )
            .where(
                TokenUsageRecord.tenant_id == principal.tenant_id,
                TokenUsageRecord.created_at >= since,
            )
            .group_by(TokenUsageRecord.model_provider, TokenUsageRecord.model_name)
            .order_by(func.sum(TokenUsageRecord.total_tokens).desc())
        ))

        cost_per_1k_prompt = self._settings.llm_cost_per_1k_prompt
        cost_per_1k_completion = self._settings.llm_cost_per_1k_completion

        breakdown = []
        total_prompt = total_completion = total_cost_usd = 0.0
        for row in rows:
            pt = int(row.prompt_tokens or 0)
            ct = int(row.completion_tokens or 0)
            cost = (pt / 1000 * cost_per_1k_prompt) + (ct / 1000 * cost_per_1k_completion)
            total_prompt += pt
            total_completion += ct
            total_cost_usd += cost
            breakdown.append({
                "modelProvider": row.model_provider,
                "modelName": row.model_name,
                "promptTokens": pt,
                "completionTokens": ct,
                "totalTokens": pt + ct,
                "calls": int(row.calls or 0),
                "estimatedCostUsd": round(cost, 4),
            })

        # Daily token usage for the chart
        daily_rows = list(self._session.execute(
            select(
                func.date(TokenUsageRecord.created_at).label("day"),
                func.sum(TokenUsageRecord.total_tokens).label("tokens"),
            )
            .where(
                TokenUsageRecord.tenant_id == principal.tenant_id,
                TokenUsageRecord.created_at >= since,
            )
            .group_by(func.date(TokenUsageRecord.created_at))
            .order_by(func.date(TokenUsageRecord.created_at))
        ))

        return {
            "periodDays": days,
            "totalPromptTokens": int(total_prompt),
            "totalCompletionTokens": int(total_completion),
            "totalTokens": int(total_prompt + total_completion),
            "estimatedCostUsd": round(total_cost_usd, 4),
            "costPer1kPromptUsd": cost_per_1k_prompt,
            "costPer1kCompletionUsd": cost_per_1k_completion,
            "breakdown": breakdown,
            "dailyUsage": [
                {"day": str(r.day), "tokens": int(r.tokens or 0)}
                for r in daily_rows
            ],
        }

    # ── Retrieval quality feedback ───────────────────────────────────────────

    def record_feedback(
        self,
        principal: AuthenticatedPrincipal,
        payload: RetrievalFeedbackInput,
    ) -> dict:
        """Record a thumbs-up/down signal for a retrieved chunk at a given rank."""
        query_hash = hashlib.sha256(
            f"{principal.tenant_id}:{payload.query.strip()}".encode()
        ).hexdigest()

        record = RetrievalFeedbackRecord(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            query_hash=query_hash,
            chunk_id=payload.chunk_id,
            rank=payload.rank,
            relevant=1 if payload.relevant else 0,
        )
        self._session.add(record)
        self._session.commit()
        return {"id": record.id, "queryHash": query_hash, "recorded": True}

    def get_quality_metrics(
        self,
        principal: AuthenticatedPrincipal,
        *,
        days: int = 30,
    ) -> dict:
        """Return NDCG@10, hit-rate, and query volume for the tenant."""
        assert_permission(principal.role, Perm.AUDIT_READ)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        rows = list(self._session.scalars(
            select(RetrievalFeedbackRecord)
            .where(
                RetrievalFeedbackRecord.tenant_id == principal.tenant_id,
                RetrievalFeedbackRecord.created_at >= since,
            )
            .order_by(
                RetrievalFeedbackRecord.query_hash,
                RetrievalFeedbackRecord.rank,
            )
        ))

        if not rows:
            return {
                "periodDays": days,
                "queryCount": 0,
                "feedbackCount": 0,
                "ndcgAt10": None,
                "hitRateAt10": None,
            }

        # Group by query_hash → compute NDCG@10 per query → average
        from collections import defaultdict
        by_query: dict[str, list[RetrievalFeedbackRecord]] = defaultdict(list)
        for row in rows:
            by_query[row.query_hash].append(row)

        ndcg_scores, hit_rates = [], []
        for feedback_list in by_query.values():
            sorted_by_rank = sorted(feedback_list, key=lambda r: r.rank)
            top10 = [r.relevant for r in sorted_by_rank[:10]]

            # DCG@10
            dcg = sum(
                rel / math.log2(i + 2)
                for i, rel in enumerate(top10)
            )
            # Ideal DCG@10
            ideal = sorted(top10, reverse=True)
            idcg = sum(
                rel / math.log2(i + 2)
                for i, rel in enumerate(ideal)
            )
            ndcg = (dcg / idcg) if idcg > 0 else 0.0
            ndcg_scores.append(ndcg)
            hit_rates.append(1 if any(top10) else 0)

        return {
            "periodDays": days,
            "queryCount": len(by_query),
            "feedbackCount": len(rows),
            "ndcgAt10": round(sum(ndcg_scores) / len(ndcg_scores), 4),
            "hitRateAt10": round(sum(hit_rates) / len(hit_rates), 4),
        }
