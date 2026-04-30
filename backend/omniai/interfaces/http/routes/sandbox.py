"""Sandbox execution route — demo endpoint for the Deploy Manager presentation.

POST /v1/sandbox/run
  Accepts Python code, executes it in the SubprocessSandbox, returns stdout/stderr/artifacts.
  Requires authentication (admin or higher). Not rate-limited beyond the global limit.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.interfaces.http.deps import get_current_principal
from omniai.interfaces.http.envelope import ok
from omniai.ports.sandbox import SandboxRequest

router = APIRouter(prefix="/v1/sandbox", tags=["sandbox"])


class SandboxRunRequest(BaseModel):
    code: str = Field(min_length=1, description="Python source code to execute")
    timeout_seconds: float = Field(default=10.0, ge=0.5, le=30.0)
    files: dict[str, str] = Field(
        default_factory=dict,
        description="Optional seed files as {relative_path: text_content}",
    )


class SandboxRunResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    artifacts: dict[str, str]  # path -> base64 or text preview


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_sandbox(
    body: SandboxRunRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> dict:
    sandbox = request.app.state.container.sandbox
    if sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Sandbox is disabled. Set SANDBOX_KIND=subprocess in your .env "
                "and restart the server."
            ),
        )

    seed_files: dict[str, bytes] = {
        path: content.encode("utf-8") for path, content in body.files.items()
    }

    result = await sandbox.run(
        SandboxRequest(
            code=body.code,
            language="python",
            timeout_seconds=body.timeout_seconds,
            files=seed_files,
        )
    )

    # Decode artifacts to text where possible (truncate large blobs to 4 KiB preview)
    artifact_previews: dict[str, str] = {}
    for path, data in result.artifacts.items():
        try:
            artifact_previews[path] = data.decode("utf-8", errors="replace")[:4096]
        except Exception:
            artifact_previews[path] = f"<binary {len(data)} bytes>"

    return ok(
        {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": round(result.duration_seconds, 3),
            "timed_out": result.timed_out,
            "artifacts": artifact_previews,
        }
    )
