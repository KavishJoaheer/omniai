from fastapi import APIRouter, Depends, HTTPException, status

from omniai.application.auth_service import AuthService, CreateTeamInput
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/teams", tags=["teams"])


@router.get("")
def list_teams(
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.list_teams(principal))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_team(
    payload: CreateTeamInput,
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.create_team(principal, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ok(result, message="created")
