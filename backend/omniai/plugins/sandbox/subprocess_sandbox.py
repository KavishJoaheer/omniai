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
    """Subprocess-based multi-language sandbox.

    Supports the following languages via the ``language`` field on
    ``SandboxRequest``:

    * ``"python"``     — runs via ``sys.executable -I``
    * ``"javascript"`` — runs via ``node`` (Node.js must be on PATH)
    * ``"bash"``       — runs via ``bash`` (POSIX systems only)

    Each run gets:
      - a fresh temporary directory as the working directory
      - a scrubbed environment (no inherited secrets)
      - an asyncio-enforced timeout
      - artifact collection from any files written to the tempdir

    This is NOT a kernel-level sandbox. For untrusted code in production,
    swap in the Docker or gVisor backend behind the same ``SandboxPort``
    interface — call sites are unchanged.
    """

    name = "subprocess"

    # ── language → (cmd_builder, script_filename) ────────────────────────────

    _SUPPORTED = {"python", "javascript", "bash"}

    def _build_cmd(self, language: str, script_path: Path) -> list[str]:
        if language == "python":
            return [sys.executable, "-I", str(script_path)]
        if language == "javascript":
            node = shutil.which("node") or shutil.which("nodejs")
            if node is None:
                raise FileNotFoundError("node executable not found on PATH")
            return [node, str(script_path)]
        if language == "bash":
            bash = shutil.which("bash")
            if bash is None:
                raise FileNotFoundError("bash executable not found on PATH")
            return [bash, str(script_path)]
        raise ValueError(f"unsupported language: {language!r}")

    def _script_name(self, language: str) -> str:
        return {"python": "_run.py", "javascript": "_run.js", "bash": "_run.sh"}.get(language, "_run")

    async def run(self, request: SandboxRequest) -> SandboxResult:
        if request.language not in self._SUPPORTED:
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=f"unsupported language: {request.language!r}. Supported: {', '.join(sorted(self._SUPPORTED))}",
                duration_seconds=0.0,
            )

        workdir = Path(tempfile.mkdtemp(prefix="omniai-sbx-"))
        # Seed any inputs into the workdir
        for relative, content in (request.files or {}).items():
            target = workdir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        script_name = self._script_name(request.language)
        script_path = workdir / script_name
        script_path.write_text(request.code, encoding="utf-8")

        # Scrubbed environment — only minimal vars
        env: dict[str, str] = {
            "PATH": os.environ.get("PATH", ""),
            "TMPDIR": str(workdir),
        }
        if request.language == "python":
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        if sys.platform == "win32":
            for required in ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"):
                value = os.environ.get(required)
                if value:
                    env[required] = value

        try:
            cmd = self._build_cmd(request.language, script_path)
        except (FileNotFoundError, ValueError) as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            return SandboxResult(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=0.0,
            )

        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
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
        # script file we seeded plus the files we seeded ourselves.
        seeded = {script_name, *(request.files or {}).keys()}
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
