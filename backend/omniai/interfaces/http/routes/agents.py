from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

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
