"""gVisor-isolated sandbox.

Runs code inside a gVisor (``runsc``) container for kernel-level isolation
beyond what Docker alone provides.  gVisor intercepts all system calls via
a user-space kernel, providing a smaller attack surface against container
escape exploits.

Requirements
------------
* ``runsc`` binary on PATH (or configured via ``GVISOR_RUNSC_BIN`` setting).
* Docker daemon available (``runsc`` is used as a Docker runtime).
* The ``docker`` CLI on PATH.

Graceful degradation
--------------------
If ``runsc`` is not found on PATH or the runtime is not available, the
constructor raises ``RuntimeError`` with a clear message so the factory can
fall back to DockerSandbox or SubprocessSandbox.

gVisor-specific security properties
------------------------------------
* All syscalls are intercepted by the Sentry (gVisor's user-space kernel).
* The host kernel is not directly exposed to container processes.
* ``--network=none`` disables all outbound/inbound network connectivity.
* Memory and CPU caps mirror the DockerSandbox configuration.

Supported languages
-------------------
Same as SubprocessSandbox: ``python``, ``javascript``, ``bash``.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import shutil
import tarfile
import time

from omniai.ports.sandbox import SandboxRequest, SandboxResult

logger = logging.getLogger(__name__)

_IMAGE = os.environ.get("SANDBOX_GVISOR_IMAGE", "python:3.11-slim")
_MAX_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MiB

_LANGUAGE_CMD: dict[str, str] = {
    "python":     "python -I /workspace/_run.py",
    "javascript": "node /workspace/_run.js",
    "bash":       "bash /workspace/_run.sh",
}
_SCRIPT_NAME: dict[str, str] = {
    "python":     "_run.py",
    "javascript": "_run.js",
    "bash":       "_run.sh",
}


class GVisorSandbox:
    """Container-isolated sandbox using gVisor (``runsc``) as the Docker runtime."""

    name = "gvisor"

    def __init__(self, runsc_bin: str = "runsc") -> None:
        # Validate at construction time so the factory fails fast.
        if shutil.which(runsc_bin) is None:
            raise RuntimeError(
                f"gVisor runsc binary not found: {runsc_bin!r}. "
                "Install gVisor (https://gvisor.dev/docs/user_guide/install/) "
                "or set GVISOR_RUNSC_BIN to the correct path."
            )
        self._runsc_bin = runsc_bin

    async def run(self, request: SandboxRequest) -> SandboxResult:
        language = request.language
        if language not in _LANGUAGE_CMD:
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"unsupported language: {language!r}. Supported: {', '.join(sorted(_LANGUAGE_CMD))}",
                duration_seconds=0.0,
            )

        bundle = self._build_bundle(request)

        cmd = [
            "docker", "run",
            "--rm",
            "--runtime", "runsc",         # ← gVisor runtime
            "--network", "none",
            "--read-only",
            "--tmpfs", "/workspace:rw,exec,size=128m",
            "--tmpfs", "/tmp:rw,noexec,size=64m",
            "--memory", "256m",
            "--memory-swap", "256m",
            "--cpus", "0.5",
            "--no-new-privileges",
            "--user", "1000:1000",
            "--workdir", "/workspace",
            "--interactive",
            _IMAGE,
            "sh", "-c",
            f'printf "%s" "$BUNDLE" | base64 -d | tar -xz -C /workspace && {_LANGUAGE_CMD[language]}',
        ]

        env = {**os.environ, "BUNDLE": bundle}

        started = time.perf_counter()
        timed_out = False
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
            )
        except FileNotFoundError:
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr="Docker executable not found. Is Docker installed and on PATH?",
                duration_seconds=0.0,
            )
        except Exception as exc:
            logger.exception("gvisor sandbox: failed to spawn container")
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"failed to start gVisor container: {exc}",
                duration_seconds=0.0,
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(), timeout=request.timeout_seconds
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            stdout_b = b""
            stderr_b = b"[sandbox timed out]".encode()

        duration = time.perf_counter() - started
        stdout = stdout_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        stderr = stderr_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")

        return SandboxResult(
            exit_code=process.returncode if process.returncode is not None else 1,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            timed_out=timed_out,
            artifacts={},
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_bundle(request: SandboxRequest) -> str:
        script_name = _SCRIPT_NAME[request.language]
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for relative, content in (request.files or {}).items():
                info = tarfile.TarInfo(name=relative)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            code_bytes = request.code.encode("utf-8")
            info = tarfile.TarInfo(name=script_name)
            info.size = len(code_bytes)
            tar.addfile(info, io.BytesIO(code_bytes))
        return base64.b64encode(buf.getvalue()).decode("ascii")
