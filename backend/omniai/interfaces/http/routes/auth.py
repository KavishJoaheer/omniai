from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from omniai.application.auth_service import AuthService, LoginInput, RegisterInput
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class PasswordResetRequestInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetInput(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=256)


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

    # When MFA is enabled the service returns a challenge token instead of a
    # full session — skip cookie-setting in that case.
    if result.get("mfaRequired"):
        return ok(result)

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
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    # Revoke the token in the DB blocklist so it can't be replayed
    settings = auth_service._settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
    if token:
        auth_service.logout(token)

    response.delete_cookie(settings.session_cookie_name)
    return ok({"loggedOut": True})


@router.get("/me")
def me(principal=Depends(get_current_principal)) -> dict:
    return ok(AuthService.principal_to_payload(principal))


@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequestInput,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """Initiate a password reset.

    Always returns 202 regardless of whether the email exists, to prevent
    user enumeration.  In production, deliver the token via email.
    For this build, the token is returned directly in the response body
    so it can be used from the admin console without an SMTP server.
    """
    token = auth_service.request_password_reset(payload.email)
    # Return the token in the response (dev-mode convenience).
    # In production: send email and return {"message": "Check your inbox."}.
    return ok({
        "message": "If that address is registered you will receive a reset link.",
        "reset_token": token,   # omit this field when SMTP is wired up
    })


@router.post("/reset-password")
def reset_password(
    payload: PasswordResetInput,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        auth_service.reset_password(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok({"message": "Password updated successfully."})
