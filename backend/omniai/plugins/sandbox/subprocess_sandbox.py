from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from omniai.ports.sandbox import SandboxRequest, SandboxResult

logger = logging.getLogger(__name__)


class SubprocessSandbox:
    """Subprocess-based Python sandbox.

    Runs the supplied code as a separate Python process with:
      - a fresh, scrubbed environment (no inherited secrets)
      - cwd set to a tempdir; deleted after the run
      - no shell — argv is built directly
      - asyncio-enforced timeout
      - artifacts collected from any files the code wrote into the tempdir

    This is NOT a kernel-level sandbox. The child process can still touch the
    host filesystem outside its tempdir if it really tries (no chroot/seccomp
    here). For untrusted code in production, swap in a Docker/gVisor backend
    behind the same `SandboxPort` interface — call sites are unchanged.

    Why this exists: it gives us a usable Code-node-runner today on every OS
    where Python runs (Win/macOS/Linux) and lets the demo show the contract.
    """

    name = "subprocess"

    async def run(self, request: SandboxRequest) -> SandboxResult:
        if request.language != "python":
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"unsupported language: {request.language!r}",
                duration_seconds=0.0,
            )

        workdir = Path(tempfile.mkdtemp(prefix="omniai-sbx-"))
        # Seed any inputs into /workspace
        for relative, content in (request.files or {}).items():
            target = workdir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        script_path = workdir / "_run.py"
        script_path.write_text(request.code, encoding="utf-8")

        # Scrubbed environment — only what's strictly needed for Python to run
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(workdir),
        }
        if sys.platform == "win32":
            for required in ("SYSTEMROOT", "SYSTEMDRIVE"):
                value = os.environ.get(required)
                if value:
                    env[required] = value

        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",  # isolated mode: ignore PYTHON* env, no user site
                str(script_path),
                cwd=str(workdir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            logger.exception("sandbox: failed to spawn process")
            shutil.rmtree(workdir, ignore_errors=True)
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"failed to start sandbox: {exc}",
                duration_seconds=0.0,
            )

        timed_out = False
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
            stderr_b = b""

        duration = time.perf_counter() - started

        # Collect any artifacts the code wrote to the tempdir, EXCLUDING the
        # _run.py we seeded plus the files we seeded ourselves.
        seeded = {"_run.py", *(request.files or {}).keys()}
        artifacts: dict[str, bytes] = {}
        for path in workdir.rglob("*"):
            if not path.is_file():
                continue
            relative = str(path.relative_to(workdir)).replace("\\", "/")
            if relative in seeded:
                continue
            try:
                # Cap individual artifact size at 5 MiB to avoid memory blowup
                size = path.stat().st_size
                if 0 < size <= 5 * 1024 * 1024:
                    artifacts[relative] = path.read_bytes()
            except OSError:
                continue

        shutil.rmtree(workdir, ignore_errors=True)

        return SandboxResult(
            exit_code=process.returncode if process.returncode is not None else 1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            duration_seconds=duration,
            timed_out=timed_out,
            artifacts=artifacts,
        )
