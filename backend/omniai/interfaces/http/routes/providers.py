from fastapi import APIRouter, Depends, HTTPException, status

from omniai.application.provider_service import (
    CreateProviderInput,
    ProviderService,
    UpdateProviderInput,
)
from omniai.interfaces.http.deps import get_current_principal, get_provider_service, principal_to_provider_actor
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/providers", tags=["providers"])


@router.get("")
def list_providers(
    principal=Depends(get_current_principal),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    actor = principal_to_provider_actor(principal)
    try:
        return ok(service.list_providers(actor))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: CreateProviderInput,
    principal=Depends(get_current_principal),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    actor = principal_to_provider_actor(principal)
    try:
        return ok(service.create_provider(actor, payload), message="created")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/{provider_id}")
def update_provider(
    provider_id: str,
    payload: UpdateProviderInput,
    principal=Depends(get_current_principal),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    actor = principal_to_provider_actor(principal)
    try:
        return ok(service.update_provider(actor, provider_id, payload))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{provider_id}")
def delete_provider(
    provider_id: str,
    principal=Depends(get_current_principal),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    actor = principal_to_provider_actor(principal)
    try:
        service.delete_provider(actor, provider_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok({"deleted": True})


@router.get("/{provider_id}/models")
def list_provider_models(
    provider_id: str,
    principal=Depends(get_current_principal),
    service: ProviderService = Depends(get_provider_service),
) -> dict:
    actor = principal_to_provider_actor(principal)
    try:
        models = service.list_models(actor, provider_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ok({"models": models})
