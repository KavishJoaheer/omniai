from __future__ import annotations

import logging

from omniai.config.settings import Settings
from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
from omniai.ports.sandbox import SandboxPort

logger = logging.getLogger(__name__)


def build_sandbox(settings: Settings) -> SandboxPort | None:
    """Build the configured sandbox backend.

    settings.sandbox_kind (SANDBOX_KIND env var):
      - "none" / "" / unset → return None (Code nodes will refuse to run)
      - "subprocess"        → SubprocessSandbox (OS-process isolation; supports
                              Python, JavaScript, Bash; safe for trusted / dev)
      - "docker"            → DockerSandbox (kernel-namespace isolation via
                              Docker; requires Docker daemon on the host;
                              recommended for untrusted code in production)
      - "gvisor"            → GVisorSandbox (Docker + gVisor runsc runtime for
                              syscall-level isolation; requires runsc on PATH)
    """
    kind = (getattr(settings, "sandbox_kind", "") or "").lower().strip()
    if kind in ("", "none"):
        return None
    if kind == "subprocess":
        return SubprocessSandbox()
    if kind == "docker":
        from omniai.plugins.sandbox.docker_sandbox import DockerSandbox
        logger.info("sandbox: using Docker backend (image=%s)", "python:3.11-slim")
        return DockerSandbox()
    if kind == "gvisor":
        from omniai.plugins.sandbox.gvisor_sandbox import GVisorSandbox
        runsc_bin = getattr(settings, "gvisor_runsc_bin", "runsc") or "runsc"
        try:
            sandbox = GVisorSandbox(runsc_bin=runsc_bin)
            logger.info("sandbox: using gVisor backend (runsc=%s)", runsc_bin)
            return sandbox
        except RuntimeError as exc:
            logger.error("sandbox: gVisor unavailable (%s); falling back to subprocess", exc)
            return SubprocessSandbox()
    logger.warning("sandbox: unknown SANDBOX_KIND=%r, sandbox disabled", kind)
    return None
