from __future__ import annotations

import asyncio
import base64
import logging
import os
import time

from omniai.ports.sandbox import SandboxRequest, SandboxResult

"""Docker-based Python sandbox.

Runs each code snippet inside a disposable ``python:3.11-slim`` container
with all network access disabled and strict resource caps.  This provides
kernel-namespace isolation on Linux (and Linux VM-backed runtimes on
macOS/Windows) that the subprocess sandbox cannot offer.

Requirements
------------
* Docker daemon reachable (``/var/run/docker.sock`` or ``DOCKER_HOST``).
* The ``docker`` Python package installed (``pip install docker``).

Graceful degradation
--------------------
If Docker is not available (daemon unreachable, package not installed) the
adapter raises ``RuntimeError`` at call time so the calling agent-node can
surface a clear "sandbox unavailable" error rather than silently falling back
to less-isolated execution.

Security properties
-------------------
* ``--network none``       — no outbound/inbound network
* ``--read-only``          — root filesystem is immutable
* ``--tmpfs /tmp``         — writable scratchpad only in memory
* ``--memory 256m``        — OOM-killed if the script goes over
* ``--cpus 0.5``           — throttled to half a CPU
* ``--no-new-privileges``  — prevent privilege escalation via setuid
* ``--user 1000:1000``     — run as unprivileged user
* Container is always ``--rm`` (auto-deleted on exit).
"""



logger = logging.getLogger(__name__)

_IMAGE = os.environ.get("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
_MAX_OUTPUT_BYTES = 1 * 1024 * 1024   # 1 MiB — prevent log flooding
_MAX_ARTIFACT_BYTES = 5 * 1024 * 1024  # 5 MiB per artifact


class DockerSandbox:
    """Container-isolated Python sandbox via Docker."""

    name = "docker"

    async def run(self, request: SandboxRequest) -> SandboxResult:
        if request.language != "python":
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"unsupported language: {request.language!r}",
                duration_seconds=0.0,
            )

        # Build a self-contained script bundle as a base64-encoded tar so we
        # can pass it via stdin without needing a volume mount.
        bundle = self._build_bundle(request)

        cmd = [
            "docker", "run",
            "--rm",
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
            "--interactive",          # we pipe stdin
            _IMAGE,
            "sh", "-c",
            # Decode the base64 bundle, unpack it, then run _run.py.
            # Using printf instead of echo to avoid issues with special chars.
            "printf '%s' \"$BUNDLE\" | base64 -d | tar -xz -C /workspace && python -I /workspace/_run.py",
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
            logger.exception("docker sandbox: failed to spawn container")
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"failed to start container: {exc}",
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

        # Artifacts: Docker --read-only + tmpfs means any files written by the
        # script land in /workspace (tmpfs).  We can't read them back without
        # an explicit volume mount, so artifacts are not supported in this
        # backend.  Use subprocess sandbox if artifact collection is needed.
        return SandboxResult(
            exit_code=process.returncode if process.returncode is not None else 1,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            timed_out=timed_out,
            artifacts={},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_bundle(request: SandboxRequest) -> str:
        """Return a base64-encoded .tar.gz containing _run.py + any seed files."""
        import io
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Seed files
            for relative, content in (request.files or {}).items():
                info = tarfile.TarInfo(name=relative)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            # Main script
            code_bytes = request.code.encode("utf-8")
            info = tarfile.TarInfo(name="_run.py")
            info.size = len(code_bytes)
            tar.addfile(info, io.BytesIO(code_bytes))
        return base64.b64encode(buf.getvalue()).decode("ascii")
