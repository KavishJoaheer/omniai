from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class SandboxRequest:
    code: str
    language: str = "python"  # currently only "python" is supported
    timeout_seconds: float = 30.0
    memory_mb: int = 512
    network_allowlist: list[str] = field(default_factory=list)  # reserved for stricter sandboxes
    files: dict[str, bytes] = field(default_factory=dict)       # path -> contents to seed /workspace


@dataclass(slots=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    artifacts: dict[str, bytes] = field(default_factory=dict)   # path -> bytes for files written


class SandboxPort(Protocol):
    """Confined execution environment for agent-emitted code.

    Implementations must NEVER inherit the host process's environment, working
    directory, or filesystem write permissions. Errors during sandbox setup
    should be reflected in `SandboxResult.exit_code != 0` rather than raised,
    so the agent runtime can surface them gracefully to the caller.
    """

    name: str

    async def run(self, request: SandboxRequest) -> SandboxResult: ...
