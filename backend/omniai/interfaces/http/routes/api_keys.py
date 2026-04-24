from fastapi import APIRouter, Depends, HTTPException, status

from omniai.application.auth_service import AuthService, CreateApiKeyInput
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.get("")
def list_api_keys(
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.list_api_keys(principal))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: CreateApiKeyInput,
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.create_api_key(principal, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ok(result, message="created")


@router.post("/{api_key_id}/revoke")
def revoke_api_key(
    api_key_id: str,
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.revoke_api_key(principal, api_key_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ok(result)
