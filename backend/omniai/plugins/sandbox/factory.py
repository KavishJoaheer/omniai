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
      - "subprocess"        → SubprocessSandbox (OS-process isolation only;
                              safe for trusted or development workloads)
      - "docker"            → DockerSandbox (kernel-namespace isolation via
                              Docker; requires Docker daemon on the host;
                              recommended for untrusted code in production)
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
    logger.warning("sandbox: unknown SANDBOX_KIND=%r, sandbox disabled", kind)
    return None
