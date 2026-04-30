from __future__ import annotations

import logging

from omniai.config.settings import Settings
from omniai.plugins.sandbox.subprocess_sandbox import SubprocessSandbox
from omniai.ports.sandbox import SandboxPort

logger = logging.getLogger(__name__)


def build_sandbox(settings: Settings) -> SandboxPort | None:
    """Build the configured sandbox backend.

    settings.sandbox_kind:
      - "none" / "" / unset → return None (Code nodes will refuse to run)
      - "subprocess"        → SubprocessSandbox (process isolation only)
      - "docker"            → DockerSandbox (kernel-namespace isolation,
                              not yet implemented — falls back to subprocess
                              with a warning so you don't lose the route)
    """
    kind = (getattr(settings, "sandbox_kind", "") or "").lower().strip()
    if kind in ("", "none"):
        return None
    if kind == "subprocess":
        return SubprocessSandbox()
    if kind == "docker":
        # Phase 2: this should spawn a Docker container per call.
        logger.warning(
            "sandbox_kind=docker requested but Docker backend isn't built yet; "
            "falling back to subprocess sandbox"
        )
        return SubprocessSandbox()
    logger.warning("sandbox: unknown SANDBOX_KIND=%r, sandbox disabled", kind)
    return None
