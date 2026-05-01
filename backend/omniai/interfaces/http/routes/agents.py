from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response as HttpResponse

from omniai.application.agent_service import AgentService, CreateAgentInput, StartAgentRunInput, UpdateAgentInput
from omniai.interfaces.http.deps import get_agent_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("")
def list_agents(
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    return ok(service.list_agents())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: CreateAgentInput,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.create_agent(payload), message="created")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{agent_id}")
def get_agent(
    agent_id: str,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.get_agent(agent_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{agent_id}")
@router.put("/{agent_id}", include_in_schema=False)
def update_agent(
    agent_id: str,
    payload: UpdateAgentInput,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.update_agent(agent_id, payload))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{agent_id}")
def delete_agent(
    agent_id: str,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.delete_agent(agent_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{agent_id}/publish")
def publish_agent(
    agent_id: str,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.publish_agent(agent_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{agent_id}/runs")
def list_agent_runs(
    agent_id: str,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.list_runs(agent_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{agent_id}/runs", status_code=status.HTTP_201_CREATED)
async def start_agent_run(
    agent_id: str,
    payload: StartAgentRunInput,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(await service.start_run(agent_id, payload), message="created")
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{agent_id}/runs/{run_id}")
def get_agent_run(
    agent_id: str,
    run_id: str,
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        return ok(service.get_run(agent_id, run_id))
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── M18: Agent run export ────────────────────────────────────────────────────

@router.get("/{agent_id}/runs/{run_id}/export")
def export_agent_run(
    agent_id: str,
    run_id: str,
    format: str = "json",  # "json" | "markdown"
    _: object = Depends(get_current_principal),
    service: AgentService = Depends(get_agent_service),
) -> HttpResponse:
    """Export an agent run as JSON or Markdown.

    - ``format=json`` → full structured run record including events.
    - ``format=markdown`` → human-readable transcript of the run.
    """
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="format must be 'json' or 'markdown'.")
    try:
        agent = service.get_agent(agent_id)
        run_data = service.get_run(agent_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Convert Pydantic models to plain dicts for serialisation
    agent_dict = agent.model_dump()
    run_dict = run_data.model_dump()

    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in agent_dict.get("name", "agent"))[:40]
    filename_base = f"{safe_name}_run_{run_id[:8]}"

    if format == "json":
        body_bytes = json.dumps(run_dict, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        return HttpResponse(
            content=body_bytes,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.json"'},
        )
    else:
        # Markdown transcript
        lines = [
            "# Agent Run Export",
            "",
            f"**Agent:** {agent_dict.get('name', agent_id)}",
            f"**Run ID:** {run_id}",
            f"**Status:** {run_dict.get('status', 'unknown')}",
            "",
        ]
        inp = run_dict.get("input") or ""
        if inp:
            lines += ["## Input", "", str(inp), ""]

        out = run_dict.get("output") or {}
        if out.get("answer"):
            lines += ["## Answer", "", out["answer"], ""]

        refs = out.get("references") or []
        if refs:
            lines += ["## Sources", ""]
            for ref in refs:
                doc_name = ref.get("documentName") or ref.get("document_name") or "doc"
                lines.append(f"- [{doc_name}] — score {ref.get('score', '')}")
            lines.append("")

        events = run_dict.get("events") or []
        if events:
            lines += ["## Execution Trace", ""]
            for ev in events:
                ts = ev.get("createdAt") or ev.get("created_at") or ""
                node = ev.get("nodeId") or ev.get("node_id") or "?"
                evt = ev.get("event") or ""
                lines.append(f"- `{ts}` **{node}** → {evt}")
            lines.append("")

        body_bytes = "\n".join(lines).encode("utf-8")
        return HttpResponse(
            content=body_bytes,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.md"'},
        )
