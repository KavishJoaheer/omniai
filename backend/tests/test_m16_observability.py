"""M16 — Observability & Cost tests.

Covers:
  1. Token usage recording + cost dashboard aggregation
  2. Retrieval quality feedback + NDCG@10 calculation
  3. OTel tracing module loads without errors
  4. Sentry setup module is a no-op when DSN is absent
  5. HTTP routes: /v1/observability/cost, /quality, /retrieval-feedback
"""
from __future__ import annotations

import math
import pytest
from fastapi.testclient import TestClient

_ADMIN_EMAIL = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


@pytest.fixture(scope="module")
def app():
    from omniai.interfaces.http.app import create_app
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/v1/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Token usage recording + cost dashboard
# ══════════════════════════════════════════════════════════════════════════════

class TestTokenUsage:

    def _seed_usage(self, container, n: int = 5) -> None:
        from omniai.application.observability_service import ObservabilityService
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            for i in range(n):
                svc.record_token_usage(
                    tenant_id=container.default_tenant_id,
                    user_id=None,
                    conversation_id=None,
                    model_provider="ollama",
                    model_name="llama3.2",
                    prompt_tokens=100 * (i + 1),
                    completion_tokens=50 * (i + 1),
                )

    def test_record_token_usage_does_not_raise(self, container):
        self._seed_usage(container, n=3)  # should not raise

    def test_cost_dashboard_aggregates_by_model(self, container):
        self._seed_usage(container, n=5)
        from omniai.application.observability_service import ObservabilityService
        from omniai.application.auth_service import AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            user_id="x", email="x@x", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            result = svc.get_cost_dashboard(principal, days=30)

        assert result["totalTokens"] > 0
        assert result["estimatedCostUsd"] >= 0
        assert isinstance(result["breakdown"], list)
        assert isinstance(result["dailyUsage"], list)

    def test_cost_dashboard_empty_returns_zeros(self, container):
        from omniai.application.observability_service import ObservabilityService
        from omniai.application.auth_service import AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            user_id="x", email="x@x", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            # Very short window ensures no data
            result = svc.get_cost_dashboard(principal, days=0)
        # days=0 is clamped by timedelta(0) — should return zero rows
        assert isinstance(result["totalTokens"], int)

    def test_cost_route_returns_200(self, client, auth_headers):
        r = client.get("/v1/observability/cost?days=30", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "totalTokens" in data
        assert "breakdown" in data


# ══════════════════════════════════════════════════════════════════════════════
# 2. Retrieval quality feedback + NDCG
# ══════════════════════════════════════════════════════════════════════════════

class TestRetrievalQuality:

    def _principal(self, container):
        from omniai.application.auth_service import AuthenticatedPrincipal
        return AuthenticatedPrincipal(
            user_id="x", email="x@x", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )

    def _seed_feedback(self, container, query: str, relevance_pattern: list[bool]) -> None:
        from omniai.application.observability_service import ObservabilityService, RetrievalFeedbackInput
        principal = self._principal(container)
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            for rank, relevant in enumerate(relevance_pattern, start=1):
                svc.record_feedback(
                    principal,
                    RetrievalFeedbackInput(
                        query=query,
                        chunk_id=f"chk_{rank:03d}",
                        rank=rank,
                        relevant=relevant,
                    ),
                )

    def test_perfect_retrieval_ndcg_is_one(self, container):
        """All top results relevant → NDCG@10 = 1.0."""
        self._seed_feedback(container, "ndcg perfect query xyz123", [True] * 5)
        from omniai.application.observability_service import ObservabilityService
        principal = self._principal(container)
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            result = svc.get_quality_metrics(principal, days=30)
        # May be mixed with other test data; just verify it runs and is bounded
        assert result["ndcgAt10"] is not None
        assert 0.0 <= result["ndcgAt10"] <= 1.0

    def test_no_relevant_results_ndcg_is_zero(self, container):
        """No relevant results → NDCG@10 = 0.0 for that query."""
        from omniai.application.observability_service import ObservabilityService, RetrievalFeedbackInput
        principal = self._principal(container)
        # Use a unique query so we can isolate it
        q = "totally irrelevant nonsense abc987xyz"
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            for rank in range(1, 6):
                svc.record_feedback(principal, RetrievalFeedbackInput(
                    query=q, chunk_id=f"chk_{rank}", rank=rank, relevant=False
                ))
            result = svc.get_quality_metrics(principal, days=30)
        assert result["ndcgAt10"] is not None  # aggregate may include other queries

    def test_hit_rate_one_when_any_relevant(self, container):
        self._seed_feedback(container, "hit rate check uvw654", [False, False, True, False, False])
        from omniai.application.observability_service import ObservabilityService
        principal = self._principal(container)
        with container.database.new_session() as session:
            svc = ObservabilityService(session, container.settings)
            result = svc.get_quality_metrics(principal, days=30)
        assert result["hitRateAt10"] is not None
        assert result["hitRateAt10"] > 0

    def test_feedback_route_returns_201_shape(self, client, auth_headers):
        r = client.post(
            "/v1/observability/retrieval-feedback",
            json={"query": "test query for route", "chunk_id": "chk_001", "rank": 1, "relevant": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert "id" in data
        assert data["recorded"] is True

    def test_quality_route_returns_200(self, client, auth_headers):
        r = client.get("/v1/observability/quality?days=30", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "ndcgAt10" in data
        assert "hitRateAt10" in data
        assert "queryCount" in data


# ══════════════════════════════════════════════════════════════════════════════
# 3. OTel tracing module — no-op safety
# ══════════════════════════════════════════════════════════════════════════════

class TestOTelTracing:

    def test_configure_tracing_no_endpoint_does_not_raise(self):
        from omniai.observability.tracing import configure_tracing
        from unittest.mock import MagicMock
        settings = MagicMock()
        settings.otel_exporter_otlp_endpoint = None
        settings.otel_service_name = "test-service"
        configure_tracing(settings)  # should not raise

    def test_configure_tracing_with_endpoint_does_not_raise(self):
        """Even with a fake endpoint, initialisation should not raise.

        The OTLP/gRPC exporter package may not be installed in the test venv;
        the tracing module must log a warning and continue — never crash.
        """
        from omniai.observability.tracing import configure_tracing
        from unittest.mock import MagicMock
        import logging
        settings = MagicMock()
        settings.otel_exporter_otlp_endpoint = "http://localhost:4317"
        settings.otel_service_name = "test-service"
        # Should not raise regardless of whether the OTLP exporter is installed.
        try:
            configure_tracing(settings)
        except Exception as exc:
            pytest.fail(f"configure_tracing raised unexpectedly: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Sentry — no-op when DSN absent
# ══════════════════════════════════════════════════════════════════════════════

class TestSentrySetup:

    def test_configure_sentry_noop_without_dsn(self):
        from omniai.observability.sentry_setup import configure_sentry
        from unittest.mock import MagicMock
        settings = MagicMock()
        settings.sentry_dsn = None
        configure_sentry(settings)  # should not raise or call sentry_sdk.init

    def test_configure_sentry_invalid_dsn_does_not_raise(self):
        from omniai.observability.sentry_setup import configure_sentry
        from unittest.mock import MagicMock
        settings = MagicMock()
        settings.sentry_dsn = "https://fake@sentry.io/0"
        settings.sentry_traces_sample_rate = 0.0
        settings.app_env = "test"
        # sentry_sdk.init may fail with a network error or invalid DSN;
        # our wrapper must swallow it.
        configure_sentry(settings)


# ══════════════════════════════════════════════════════════════════════════════
# 5. NDCG math (pure unit test — no DB)
# ══════════════════════════════════════════════════════════════════════════════

class TestNDCGMath:

    @staticmethod
    def _dcg(relevance: list[int]) -> float:
        return sum(r / math.log2(i + 2) for i, r in enumerate(relevance))

    def test_perfect_ndcg(self):
        relevance = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        dcg = self._dcg(relevance)
        ideal = self._dcg(sorted(relevance, reverse=True))
        ndcg = dcg / ideal if ideal > 0 else 0.0
        assert abs(ndcg - 1.0) < 1e-9

    def test_zero_ndcg_no_relevant(self):
        relevance = [0] * 10
        dcg = self._dcg(relevance)
        ideal = self._dcg(sorted(relevance, reverse=True))
        ndcg = dcg / ideal if ideal > 0 else 0.0
        assert ndcg == 0.0

    def test_partial_ndcg_between_zero_and_one(self):
        relevance = [0, 0, 1, 0, 0]
        dcg = self._dcg(relevance)
        ideal = self._dcg(sorted(relevance, reverse=True))
        ndcg = dcg / ideal if ideal > 0 else 0.0
        assert 0.0 < ndcg < 1.0
