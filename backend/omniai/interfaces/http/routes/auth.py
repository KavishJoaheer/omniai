from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from omniai.application.auth_service import AuthService, LoginInput, RegisterInput
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterInput,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.register(payload, tenant_id=request.app.state.default_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    response.set_cookie(
        key=auth_service._settings.session_cookie_name,
        value=result["accessToken"],
        httponly=True,
        samesite="lax",
        secure=auth_service._settings.app_env != "development",
        max_age=auth_service._settings.session_ttl_minutes * 60,
    )
    return ok(result, message="registered")


@router.post("/login")
def login(
    payload: LoginInput,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.login(payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    response.set_cookie(
        key=auth_service._settings.session_cookie_name,
        value=result["accessToken"],
        httponly=True,
        samesite="lax",
        secure=auth_service._settings.app_env != "development",
        max_age=auth_service._settings.session_ttl_minutes * 60,
    )
    return ok(result)


@router.post("/logout")
def logout(
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    response.delete_cookie(auth_service._settings.session_cookie_name)
    return ok({"loggedOut": True})


@router.get("/me")
def me(principal=Depends(get_current_principal)) -> dict:
    return ok(AuthService.principal_to_payload(principal))
