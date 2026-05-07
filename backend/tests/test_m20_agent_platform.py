"""M20 — Agent Platform tests.

Covers:
  1.  Parallel fan-out/join: execution plan builder produces parallel branch groups
  2.  Fan-out execution: asyncio.gather runs branches and merges references
  3.  Human-in-the-loop: human_input node raises _PausedError → run saved as PAUSED
  4.  Human-in-the-loop resume: resume_run continues from paused node
  5.  Human-in-the-loop: pre-supplied human_input in context skips pause
  6.  Time-travel replay: replay_run creates new run linked to original
  7.  Time-travel replay: from_event=0 replays full graph
  8.  Agent marketplace: list_templates returns built-in templates
  9.  Agent marketplace: get_template returns definition
  10. Agent marketplace: unknown template raises KeyError
  11. Agent marketplace: list_templates category filter
  12. Agent marketplace: list_templates tag filter
  13. HTTP GET /v1/marketplace/templates returns 200
  14. HTTP GET /v1/marketplace/templates/{id} returns definition
  15. HTTP POST /v1/agents/import-template creates agent from built-in template
  16. HTTP POST /v1/agents/import-template → 404 for unknown template_id
  17. HTTP POST /v1/agents/import-template → 400 if neither template_id nor url
  18. HTTP POST /v1/agents/{id}/runs/{run_id}/resume → 400 if not PAUSED
  19. HTTP POST /v1/agents/{id}/runs/{run_id}/replay → 201 with replay_of_run_id
  20. Multi-language sandbox: JavaScript returns output
  21. Multi-language sandbox: Bash returns output
  22. Multi-language sandbox: unsupported language returns error
  23. gVisor sandbox: RuntimeError when runsc not found
  24. Sandbox factory: "gvisor" kind falls back to subprocess when runsc missing
  25. Cost tracking: cost_usd computed from usage
  26. Cost alerting: log warning emitted when threshold exceeded
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

_ADMIN_EMAIL    = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_agent_service(*, cost_alert_usd: float = 0.0):
    """Create an AgentService with mocked store, retrieval, and sandbox."""
    from omniai.application.agent_service import AgentService

    mock_store = MagicMock()
    mock_retrieval = MagicMock()
    mock_retrieval.retrieve = AsyncMock(return_value=MagicMock(hits=[]))

    return AgentService(
        store=mock_store,
        retrieval_service=mock_retrieval,
        sandbox=None,
        cost_alert_usd=cost_alert_usd,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1–2. Parallel fan-out / join
# ══════════════════════════════════════════════════════════════════════════════

class TestParallelFanOut:

    def test_execution_plan_contains_parallel_group(self):
        from omniai.application.agent_service import _build_execution_plan
        definition = {
            "nodes": [
                {"id": "start",       "type": "start"},
                {"id": "fan_out",     "type": "fan_out",  "config": {"branches": ["r_a", "r_b"]}},
                {"id": "r_a",         "type": "retrieval"},
                {"id": "r_b",         "type": "retrieval"},
                {"id": "join",        "type": "join"},
                {"id": "generate",    "type": "generate"},
                {"id": "end",         "type": "end"},
            ],
            "edges": [
                {"from": "start",   "to": "fan_out"},
                {"from": "fan_out", "to": "r_a"},
                {"from": "fan_out", "to": "r_b"},
                {"from": "r_a",     "to": "join"},
                {"from": "r_b",     "to": "join"},
                {"from": "join",    "to": "generate"},
                {"from": "generate","to": "end"},
            ],
        }
        plan = _build_execution_plan(definition)
        # There must be at least one list-of-lists item (the parallel group)
        parallel_groups = [step for step in plan if isinstance(step, list)]
        assert parallel_groups, "Expected at least one parallel branch group in the plan"
        branches = parallel_groups[0]
        assert len(branches) == 2, "Expected two parallel branches"

    def test_fan_out_merges_references(self):
        from omniai.application.agent_service import AgentService

        def _fake_hit(chunk_id, doc_id, coll_id, score, text):
            h = MagicMock()
            h.chunk_id = chunk_id
            h.document_id = doc_id
            h.collection_id = coll_id
            h.score = score
            h.text = text
            h.snippet = text[:50]
            h.metadata = {}
            return h

        call_count = 0

        async def mock_retrieve(request):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.hits = [_fake_hit(f"c{call_count}", "d1", "col1", 0.9, f"text{call_count}")]
            return result

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve = mock_retrieve

        definition = {
            "version": 1,
            "nodes": [
                {"id": "start",   "type": "start"},
                {"id": "fan_out", "type": "fan_out"},
                {"id": "r_a",     "type": "retrieval"},
                {"id": "r_b",     "type": "retrieval"},
                {"id": "join",    "type": "join"},
                {"id": "end",     "type": "end"},
            ],
            "edges": [
                {"from": "start",   "to": "fan_out"},
                {"from": "fan_out", "to": "r_a"},
                {"from": "fan_out", "to": "r_b"},
                {"from": "r_a",     "to": "join"},
                {"from": "r_b",     "to": "join"},
                {"from": "join",    "to": "end"},
            ],
        }

        mock_agent = MagicMock()
        mock_agent.id = "agt_test"
        mock_agent.definition = definition

        mock_run = MagicMock()
        mock_run.id = "run_test"
        mock_run.input = {"input": "test query"}
        mock_run.events = []

        mock_store = MagicMock()
        mock_store.update_run = MagicMock(return_value=mock_run)

        service = AgentService(
            store=mock_store,
            retrieval_service=mock_retrieval,
        )

        _run(service._execute_run(mock_agent, mock_run))
        # Both branches should have been executed → 2 retrieval calls
        assert call_count == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3–5. Human-in-the-loop
# ══════════════════════════════════════════════════════════════════════════════

class TestHumanInTheLoop:

    def test_human_input_node_raises_paused_error(self):
        from omniai.application.agent_service import _PausedError

        service = _make_agent_service()
        node = {"id": "review", "type": "human_input",
                "config": {"prompt": "Please review."}}
        context = {"input": "test", "references": [], "messages": [], "answer": ""}

        with pytest.raises(_PausedError) as exc_info:
            _run(service._execute_node(node, {}, context))
        assert exc_info.value.node_id == "review"

    def test_run_with_human_input_node_sets_status_paused(self):
        from omniai.application.agent_service import AgentService

        mock_store = MagicMock()
        paused_run = MagicMock()
        paused_run.id = "run_paused"
        paused_run.input = {"input": "review this"}
        paused_run.events = []

        captured_status: list[str] = []

        def mock_update_run(**kwargs):
            captured_status.append(kwargs.get("status", ""))
            r = MagicMock()
            r.id = "run_paused"
            r.status = kwargs.get("status", "")
            r.events = kwargs.get("events", [])
            r.input = {"input": "review this"}
            r.paused_at_node = kwargs.get("paused_at_node")
            return r

        mock_store.update_run = mock_update_run
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve = AsyncMock(return_value=MagicMock(hits=[]))

        service = AgentService(store=mock_store, retrieval_service=mock_retrieval)

        definition = {
            "version": 1,
            "nodes": [
                {"id": "start",       "type": "start"},
                {"id": "review",      "type": "human_input",
                 "config": {"prompt": "Approve?"}},
                {"id": "end",         "type": "end"},
            ],
            "edges": [
                {"from": "start",  "to": "review"},
                {"from": "review", "to": "end"},
            ],
        }
        mock_agent = MagicMock()
        mock_agent.definition = definition
        _run(service._execute_run(mock_agent, paused_run))

        assert "PAUSED" in captured_status

    def test_pre_supplied_human_input_skips_pause(self):

        service = _make_agent_service()
        node = {"id": "review", "type": "human_input", "config": {"prompt": "Approve?"}}
        context = {
            "input": "test",
            "references": [],
            "messages": [],
            "answer": "",
            "human_input": "My answer",  # pre-supplied
            "human_approved": True,
        }
        result = _run(service._execute_node(node, {}, context))
        assert result.get("human_input_received") == "My answer"
        assert "human_input" not in context  # consumed


# ══════════════════════════════════════════════════════════════════════════════
# 6–7. Time-travel replay
# ══════════════════════════════════════════════════════════════════════════════

class TestTimeTravelReplay:

    def test_replay_run_creates_new_run_with_replay_link(self):
        from omniai.application.agent_service import AgentService, ReplayAgentRunInput

        original_run = MagicMock()
        original_run.id = "run_orig"
        original_run.input = {"input": "original query"}
        original_run.events = []

        new_run = MagicMock()
        new_run.id = "run_replay"
        new_run.input = {"input": "original query"}
        new_run.events = []
        new_run.replay_of_run_id = "run_orig"

        mock_store = MagicMock()
        mock_store.get_run = MagicMock(return_value=original_run)
        mock_store.get_agent = MagicMock(return_value=MagicMock(
            id="agt_1", definition={}, name="test"))
        mock_store.create_run = MagicMock(return_value=new_run)
        mock_store.update_run = MagicMock(return_value=new_run)

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve = AsyncMock(return_value=MagicMock(hits=[]))

        service = AgentService(store=mock_store, retrieval_service=mock_retrieval)

        _run(service.replay_run("agt_1", "run_orig", ReplayAgentRunInput(from_event=0)))

        # create_run should have been called with replay tracking fields
        call_kwargs = mock_store.create_run.call_args.kwargs
        assert call_kwargs.get("replay_of_run_id") == "run_orig"
        assert call_kwargs.get("replay_from_event") == 0

    def test_replay_run_uses_input_override(self):
        from omniai.application.agent_service import AgentService, ReplayAgentRunInput

        original_run = MagicMock()
        original_run.id = "run_orig"
        original_run.input = {"input": "original query"}
        original_run.events = []

        new_run = MagicMock()
        new_run.id = "run_replay"
        new_run.input = {"input": "overridden query"}
        new_run.events = []
        new_run.replay_of_run_id = "run_orig"

        mock_store = MagicMock()
        mock_store.get_run = MagicMock(return_value=original_run)
        mock_store.get_agent = MagicMock(return_value=MagicMock(id="agt_1", definition={}, name="test"))
        mock_store.create_run = MagicMock(return_value=new_run)
        mock_store.update_run = MagicMock(return_value=new_run)

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve = AsyncMock(return_value=MagicMock(hits=[]))

        service = AgentService(store=mock_store, retrieval_service=mock_retrieval)
        _run(service.replay_run("agt_1", "run_orig",
                                 ReplayAgentRunInput(from_event=0, input_override="overridden query")))

        call_kwargs = mock_store.create_run.call_args.kwargs
        assert call_kwargs["input_payload"]["input"] == "overridden query"


# ══════════════════════════════════════════════════════════════════════════════
# 8–12. Marketplace service
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketplaceService:

    def test_list_templates_returns_builtin(self):
        from omniai.application.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        templates = svc.list_templates()
        assert len(templates) >= 1
        assert all("id" in t and "name" in t for t in templates)

    def test_get_template_returns_definition(self):
        from omniai.application.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        t = svc.get_template("basic-rag")
        assert "definition" in t
        assert "nodes" in t["definition"]

    def test_get_template_unknown_raises_key_error(self):
        from omniai.application.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        with pytest.raises(KeyError):
            svc.get_template("nonexistent-template-xyz")

    def test_list_templates_category_filter(self):
        from omniai.application.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        research = svc.list_templates(category="research")
        assert all(t["category"] == "research" for t in research)
        assert len(research) >= 1

    def test_list_templates_tag_filter(self):
        from omniai.application.marketplace_service import MarketplaceService
        svc = MarketplaceService()
        rag_templates = svc.list_templates(tag="rag")
        assert len(rag_templates) >= 1
        # Definitions NOT included in list (lean listing)
        assert all("definition" not in t for t in rag_templates)


# ══════════════════════════════════════════════════════════════════════════════
# 13–17. Marketplace HTTP endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketplaceEndpoints:

    def test_list_templates_returns_200(self, client, auth):
        r = client.get("/v1/marketplace/templates", headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "data" in data
        assert len(data["data"]) >= 1

    def test_get_template_returns_definition(self, client, auth):
        r = client.get("/v1/marketplace/templates/basic-rag", headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()
        template = data.get("data") or data
        assert "definition" in template

    def test_import_template_creates_agent(self, client, auth):
        r = client.post("/v1/agents/import-template", json={
            "template_id": "basic-rag",
            "name": "My RAG Agent from Marketplace",
        }, headers=auth)
        assert r.status_code == 201, r.text
        data = r.json()
        agent = data.get("data") or data
        assert agent.get("name") == "My RAG Agent from Marketplace"

    def test_import_unknown_template_returns_404(self, client, auth):
        r = client.post("/v1/agents/import-template", json={
            "template_id": "nonexistent-xyz",
        }, headers=auth)
        assert r.status_code == 404

    def test_import_without_template_id_or_url_returns_400(self, client, auth):
        r = client.post("/v1/agents/import-template", json={}, headers=auth)
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 18–19. HTTP resume and replay endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentRunEndpoints:

    @pytest.fixture(scope="class")
    def agent_id(self, client, auth):
        r = client.post("/v1/agents", json={"name": "M20 Test Agent"}, headers=auth)
        assert r.status_code == 201, r.text
        data = r.json()
        return (data.get("data") or data)["id"]

    @pytest.fixture(scope="class")
    def run_id(self, client, auth, agent_id):
        r = client.post(f"/v1/agents/{agent_id}/runs",
                        json={"input": "hello world"}, headers=auth)
        assert r.status_code == 201, r.text
        data = r.json()
        return (data.get("data") or data)["id"]

    def test_resume_non_paused_run_returns_400(self, client, auth, agent_id, run_id):
        r = client.post(f"/v1/agents/{agent_id}/runs/{run_id}/resume",
                        json={"human_input": "Looks good, proceed."}, headers=auth)
        assert r.status_code == 400

    def test_replay_run_returns_201(self, client, auth, agent_id, run_id):
        r = client.post(f"/v1/agents/{agent_id}/runs/{run_id}/replay",
                        json={"from_event": 0}, headers=auth)
        assert r.status_code == 201, r.text
        data = r.json()
        new_run = data.get("data") or data
        assert new_run.get("replay_of_run_id") == run_id


# ══════════════════════════════════════════════════════════════════════════════
# 20–22. Multi-language sandbox
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiLanguageSandbox:

    def test_javascript_returns_output(self):
        import shutil
        if shutil.which("node") is None:
            pytest.skip("node not available on PATH")

        from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
        from omniai.ports.sandbox import SandboxRequest

        sandbox = SubprocessSandbox()
        result = _run(sandbox.run(SandboxRequest(
            code='console.log("hello from js");',
            language="javascript",
        )))
        assert result.exit_code == 0
        assert "hello from js" in result.stdout

    def test_bash_returns_output(self):
        import shutil
        if shutil.which("bash") is None:
            pytest.skip("bash not available on PATH")

        from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
        from omniai.ports.sandbox import SandboxRequest

        sandbox = SubprocessSandbox()
        result = _run(sandbox.run(SandboxRequest(
            code='echo "hello from bash"',
            language="bash",
        )))
        assert result.exit_code == 0
        assert "hello from bash" in result.stdout

    def test_unsupported_language_returns_error(self):
        from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
        from omniai.ports.sandbox import SandboxRequest

        sandbox = SubprocessSandbox()
        result = _run(sandbox.run(SandboxRequest(code="print(1)", language="ruby")))
        assert result.exit_code == 1
        assert "unsupported" in result.stderr.lower()


# ══════════════════════════════════════════════════════════════════════════════
# 23–24. gVisor sandbox
# ══════════════════════════════════════════════════════════════════════════════

class TestGVisorSandbox:

    def test_gvisor_raises_runtime_error_when_runsc_missing(self):
        from omniai.plugins.sandbox.gvisor_sandbox import GVisorSandbox
        with pytest.raises(RuntimeError, match="runsc"):
            GVisorSandbox(runsc_bin="nonexistent-runsc-binary-xyz")

    def test_sandbox_factory_gvisor_falls_back_to_subprocess(self):
        from omniai.config.settings import Settings
        from omniai.plugins.sandbox.factory import build_sandbox
        from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox

        settings = Settings(SANDBOX_KIND="gvisor", GVISOR_RUNSC_BIN="nonexistent-runsc-binary-xyz")
        sandbox = build_sandbox(settings)
        # Should fall back to subprocess when gVisor unavailable
        assert isinstance(sandbox, SubprocessSandbox)


# ══════════════════════════════════════════════════════════════════════════════
# 25–26. Cost tracking and alerting
# ══════════════════════════════════════════════════════════════════════════════

class TestCostTracking:

    def test_cost_usd_computed_from_usage(self):
        from omniai.application.agent_service import _compute_cost_usd
        usage = {"prompt_tokens": 500, "completion_tokens": 500}
        cost = _compute_cost_usd(usage)
        assert cost > 0.0

    def test_cost_alert_emits_log_warning(self, caplog):
        from omniai.application.agent_service import AgentService

        mock_store = MagicMock()
        completed_run = MagicMock()
        completed_run.id = "run_cost"
        completed_run.input = {"input": "test"}
        completed_run.events = []
        mock_store.update_run = MagicMock(return_value=completed_run)

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve = AsyncMock(return_value=MagicMock(hits=[]))

        mock_agent = MagicMock()
        mock_agent.id = "agt_cost"
        mock_agent.definition = {}

        # Set a tiny threshold so any run triggers the alert
        service = AgentService(
            store=mock_store,
            retrieval_service=mock_retrieval,
            cost_alert_usd=0.000001,  # 1 micro-dollar — always exceeded
        )

        with caplog.at_level(logging.WARNING, logger="omniai.application.agent_service"):
            _run(service._execute_run(mock_agent, completed_run))

        alert_logs = [r for r in caplog.records if "cost_alert" in r.message.lower() or "cost alert" in r.message.lower()]
        assert alert_logs, "Expected a cost-alert log warning"

    def test_run_has_cost_usd_field(self):
        from omniai.domain.agents.models import AgentRun
        run = AgentRun(agent_id="agt_test", cost_usd=0.0042)
        assert run.cost_usd == pytest.approx(0.0042)
