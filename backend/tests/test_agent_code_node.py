"""Tests for the agent code-node — sandbox wiring inside AgentService."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from omniai.application.agent_service import AgentService
from omniai.ports.sandbox import SandboxRequest, SandboxResult


# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------

def _make_agent_service(sandbox=None):
    """Build an AgentService with a stub store and retrieval service."""
    store = MagicMock()
    retrieval_service = MagicMock()
    retrieval_service.retrieve = AsyncMock(return_value=MagicMock(hits=[]))
    return AgentService(store=store, retrieval_service=retrieval_service, sandbox=sandbox)


def _make_stub_sandbox(stdout="", stderr="", exit_code=0, timed_out=False, artifacts=None):
    """Return a mock sandbox that resolves immediately with the given values."""
    result = SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.01,
        timed_out=timed_out,
        artifacts=artifacts or {},
    )
    sandbox = MagicMock()
    sandbox.run = AsyncMock(return_value=result)
    return sandbox


def _context(input_text="hello", references=None):
    return {
        "input": input_text,
        "references": references or [],
        "messages": [],
        "answer": "",
        "usage": {},
    }


# ---------------------------------------------------------------------------
# Code-node: happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_node_executes_and_sets_answer():
    sandbox = _make_stub_sandbox(stdout="42\n")
    svc = _make_agent_service(sandbox)
    ctx = _context()

    node = {"id": "code1", "type": "code", "config": {"code": "print(6 * 7)", "timeout_seconds": 5}}
    result = await svc._execute_node(node, _default_def(), ctx)

    assert result["exit_code"] == 0
    assert "42" in result["stdout"]
    assert ctx["answer"] == "42"   # stdout promoted to answer


@pytest.mark.asyncio
async def test_code_node_injects_context_variables():
    """Sandbox.run should receive code that includes user_input and context_text bindings."""
    sandbox = _make_stub_sandbox(stdout="ok")
    svc = _make_agent_service(sandbox)
    ctx = _context(input_text="my query", references=[{"snippet": "relevant chunk"}])

    node = {"id": "c", "type": "code", "config": {"code": "print(user_input)"}}
    await svc._execute_node(node, _default_def(), ctx)

    call_args: SandboxRequest = sandbox.run.call_args[0][0]
    assert "user_input = 'my query'" in call_args.code
    assert "context_text" in call_args.code


@pytest.mark.asyncio
async def test_code_node_returns_stderr_on_failure():
    sandbox = _make_stub_sandbox(stdout="", stderr="NameError: x", exit_code=1)
    svc = _make_agent_service(sandbox)
    node = {"id": "c", "type": "code", "config": {"code": "print(x)"}}
    result = await svc._execute_node(node, _default_def(), _context())
    assert result["exit_code"] == 1
    assert "NameError" in result["stderr"]


@pytest.mark.asyncio
async def test_code_node_returns_timeout_flag():
    sandbox = _make_stub_sandbox(stdout="", stderr="", exit_code=1, timed_out=True)
    svc = _make_agent_service(sandbox)
    node = {"id": "c", "type": "code", "config": {"code": "import time; time.sleep(99)"}}
    result = await svc._execute_node(node, _default_def(), _context())
    assert result["timed_out"] is True


@pytest.mark.asyncio
async def test_code_node_empty_stdout_does_not_override_existing_answer():
    """If the code produces no stdout, the existing answer from a prior node is preserved."""
    sandbox = _make_stub_sandbox(stdout="  \n  ")  # whitespace only
    svc = _make_agent_service(sandbox)
    ctx = _context()
    ctx["answer"] = "previous answer"

    node = {"id": "c", "type": "code", "config": {"code": "pass"}}
    await svc._execute_node(node, _default_def(), ctx)
    assert ctx["answer"] == "previous answer"


# ---------------------------------------------------------------------------
# Code-node: no sandbox configured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_node_without_sandbox_returns_error_dict():
    svc = _make_agent_service(sandbox=None)
    node = {"id": "c", "type": "code", "config": {"code": "print(1)"}}
    result = await svc._execute_node(node, _default_def(), _context())
    assert result["exit_code"] == 1
    assert "sandbox disabled" in result["stderr"].lower() or "SANDBOX_KIND" in result["stderr"]
    assert result["skipped"] is True


# ---------------------------------------------------------------------------
# Code-node: empty code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_node_with_no_code_skips():
    sandbox = _make_stub_sandbox()
    svc = _make_agent_service(sandbox)
    node = {"id": "c", "type": "code", "config": {"code": ""}}
    result = await svc._execute_node(node, _default_def(), _context())
    # Should short-circuit without calling sandbox
    sandbox.run.assert_not_called()
    assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# Code-node: artifacts surface in result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_code_node_surfaces_artifact_names():
    sandbox = _make_stub_sandbox(
        stdout="written",
        artifacts={"output.csv": b"a,b\n1,2\n"},
    )
    svc = _make_agent_service(sandbox)
    node = {"id": "c", "type": "code", "config": {"code": "..."}}
    result = await svc._execute_node(node, _default_def(), _context())
    assert "output.csv" in result["artifacts"]


# ---------------------------------------------------------------------------
# Unsupported node type still raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsupported_node_type_raises():
    svc = _make_agent_service()
    node = {"id": "x", "type": "unknown_future_type", "config": {}}
    with pytest.raises(ValueError, match="Unsupported agent node type"):
        await svc._execute_node(node, _default_def(), _context())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_def():
    from omniai.application.agent_service import DEFAULT_AGENT_DEFINITION
    import json
    return json.loads(json.dumps(DEFAULT_AGENT_DEFINITION))
