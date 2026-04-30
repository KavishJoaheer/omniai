"""Sandbox execution tests.

Coverage:
  - SubprocessSandbox: basic stdout capture
  - SubprocessSandbox: asyncio-enforced timeout → timed_out=True
  - SubprocessSandbox: artifact collection from files written in tempdir
  - SubprocessSandbox: unsupported language rejected cleanly
  - SubprocessSandbox: scrubbed environment (SECRET never leaks to child)
  - build_sandbox factory: kind="none" → None
  - build_sandbox factory: kind="subprocess" → SubprocessSandbox
  - build_sandbox factory: kind="docker" → SubprocessSandbox (fallback)
"""
from __future__ import annotations

import asyncio
import os

import pytest

from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
from omniai.ports.sandbox import SandboxRequest


# ---- helpers ----------------------------------------------------------------


def run(request: SandboxRequest):
    """Run a sandbox request synchronously for test convenience."""
    return asyncio.get_event_loop().run_until_complete(SubprocessSandbox().run(request))


# ---- basic execution --------------------------------------------------------


def test_subprocess_sandbox_captures_stdout():
    result = run(SandboxRequest(code="print('hello sandbox')"))
    assert result.exit_code == 0
    assert "hello sandbox" in result.stdout
    assert result.timed_out is False
    assert result.duration_seconds >= 0.0


def test_subprocess_sandbox_captures_stderr():
    result = run(SandboxRequest(code="import sys; sys.stderr.write('err!')"))
    assert "err!" in result.stderr
    assert result.exit_code == 0


def test_subprocess_sandbox_exit_code_on_exception():
    result = run(SandboxRequest(code="raise RuntimeError('boom')"))
    assert result.exit_code != 0
    assert "RuntimeError" in result.stderr


def test_subprocess_sandbox_multiline_code():
    code = "x = 2 + 2\nprint(f'result={x}')"
    result = run(SandboxRequest(code=code))
    assert result.exit_code == 0
    assert "result=4" in result.stdout


# ---- timeout ----------------------------------------------------------------


def test_subprocess_sandbox_enforces_timeout():
    code = "import time; time.sleep(60)"
    result = run(SandboxRequest(code=code, timeout_seconds=0.5))
    assert result.timed_out is True
    assert result.exit_code != 0


# ---- artifact collection ----------------------------------------------------


def test_subprocess_sandbox_collects_artifacts():
    code = "open('output.txt', 'w').write('artifact content')"
    result = run(SandboxRequest(code=code))
    assert result.exit_code == 0
    assert "output.txt" in result.artifacts
    assert result.artifacts["output.txt"] == b"artifact content"


def test_subprocess_sandbox_does_not_expose_run_script_as_artifact():
    """_run.py itself must never appear in the artifacts dict."""
    result = run(SandboxRequest(code="print('ok')"))
    assert "_run.py" not in result.artifacts


def test_subprocess_sandbox_seeded_files_not_in_artifacts():
    """Files we seeded into /workspace must not be echoed back as artifacts."""
    code = "print('done')"
    files = {"input.csv": b"a,b,c\n1,2,3"}
    result = run(SandboxRequest(code=code, files=files))
    assert "input.csv" not in result.artifacts


# ---- unsupported language ---------------------------------------------------


def test_subprocess_sandbox_rejects_non_python():
    result = run(SandboxRequest(code="console.log('hi')", language="javascript"))
    assert result.exit_code == 1
    assert "unsupported language" in result.stderr


# ---- scrubbed environment ---------------------------------------------------


def test_subprocess_sandbox_scrubbed_env(monkeypatch):
    """A secret in the parent process must not appear in the child's env."""
    monkeypatch.setenv("OMNIAI_SECRET_KEY", "super-secret-1234")
    code = "import os; print(os.environ.get('OMNIAI_SECRET_KEY', 'NOT_FOUND'))"
    result = run(SandboxRequest(code=code))
    assert "super-secret-1234" not in result.stdout
    assert "NOT_FOUND" in result.stdout


def test_subprocess_sandbox_scrubbed_env_no_db_url(monkeypatch):
    """DB_URL must not leak into the sandbox."""
    monkeypatch.setenv("DB_URL", "postgresql://admin:password@localhost/prod")
    code = "import os; print(os.environ.get('DB_URL', 'NONE'))"
    result = run(SandboxRequest(code=code))
    assert "password" not in result.stdout


# ---- factory ----------------------------------------------------------------


class _FakeSettings:
    sandbox_kind: str = "none"
    sandbox_default_timeout_seconds: float = 30.0


def test_build_sandbox_none():
    from omniai.plugins.sandbox.factory import build_sandbox

    settings = _FakeSettings()
    assert build_sandbox(settings) is None  # type: ignore[arg-type]


def test_build_sandbox_subprocess():
    from omniai.plugins.sandbox.factory import build_sandbox

    settings = _FakeSettings()
    settings.sandbox_kind = "subprocess"
    sb = build_sandbox(settings)  # type: ignore[arg-type]
    assert sb is not None
    assert sb.name == "subprocess"


def test_build_sandbox_docker_returns_docker_backend(caplog):
    """docker kind now returns the real DockerSandbox (M14)."""
    import logging

    from omniai.plugins.sandbox.docker_sandbox import DockerSandbox
    from omniai.plugins.sandbox.factory import build_sandbox

    settings = _FakeSettings()
    settings.sandbox_kind = "docker"
    with caplog.at_level(logging.INFO, logger="omniai.plugins.sandbox.factory"):
        sb = build_sandbox(settings)  # type: ignore[arg-type]
    assert sb is not None
    assert isinstance(sb, DockerSandbox)
    assert sb.name == "docker"


def test_build_sandbox_unknown_kind_returns_none(caplog):
    import logging

    from omniai.plugins.sandbox.factory import build_sandbox

    settings = _FakeSettings()
    settings.sandbox_kind = "hypervisor"
    with caplog.at_level(logging.WARNING, logger="omniai.plugins.sandbox.factory"):
        sb = build_sandbox(settings)  # type: ignore[arg-type]
    assert sb is None
