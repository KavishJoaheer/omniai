"""M15 — Identity & Access routes.

Mounted at /v1/auth for MFA and at /v1/invitations for invitation management.
OIDC routes live at /v1/auth/oidc/{provider}/...
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from omniai.application.auth_service import AuthService
from omniai.application.identity_service import (
    IdentityService,
    InviteAcceptInput,
    InviteCreateInput,
    MFAVerifyInput,
)
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

# ── MFA router (mounted inside /v1/auth) ─────────────────────────────────────
mfa_router = APIRouter(prefix="/v1/auth/mfa", tags=["mfa"])


def _get_identity_service(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> IdentityService:
    return IdentityService(auth_service._session, auth_service._settings)


@mfa_router.get("/status")
def mfa_status(
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    return ok(svc.mfa_status(principal))


@mfa_router.post("/setup")
def mfa_setup(
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    return ok(svc.mfa_setup(principal))


@mfa_router.post("/confirm")
def mfa_confirm(
    payload: MFAVerifyInput,
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.mfa_confirm(principal, payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result)


@mfa_router.post("/disable")
def mfa_disable(
    payload: MFAVerifyInput,
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.mfa_disable(principal, payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result)


# ── MFA verify (second factor after login challenge) ─────────────────────────

class MFAChallengeInput(BaseModel):
    challenge_token: str = Field(min_length=10)
    code: str = Field(min_length=6, max_length=8)


@mfa_router.post("/verify")
def mfa_verify(
    payload: MFAChallengeInput,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    try:
        result = auth_service.mfa_verify(payload.challenge_token, payload.code)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    settings = auth_service._settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result["accessToken"],
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "development",
        max_age=settings.session_ttl_minutes * 60,
    )
    return ok(result)


# ── Invitation router ─────────────────────────────────────────────────────────
invitations_router = APIRouter(prefix="/v1/invitations", tags=["invitations"])


@invitations_router.post("", status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InviteCreateInput,
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.create_invitation(principal, payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result, message="Invitation created.")


@invitations_router.get("")
def list_invitations(
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    return ok(svc.list_invitations(principal))


@invitations_router.post("/accept")
def accept_invitation(
    payload: InviteAcceptInput,
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.accept_invitation(payload.token, payload)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result)


@invitations_router.delete("/{invite_id}")
def revoke_invitation(
    invite_id: str,
    principal=Depends(get_current_principal),
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.revoke_invitation(principal, invite_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result)


# ── OIDC router ───────────────────────────────────────────────────────────────
oidc_router = APIRouter(prefix="/v1/auth/oidc", tags=["oidc"])


@oidc_router.get("/{provider}/authorize")
def oidc_authorize(
    provider: str,
    redirect_uri: str = Query(..., description="Where the provider should redirect after auth"),
    request: Request = None,
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    try:
        result = svc.oidc_authorization_url(provider, redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ok(result)


@oidc_router.get("/{provider}/callback")
def oidc_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    response: Response = None,
    request: Request = None,
    svc: IdentityService = Depends(_get_identity_service),
) -> dict:
    tenant_id = request.app.state.default_tenant_id
    try:
        result = svc.oidc_callback(provider, code, state, tenant_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    settings = request.app.state.container.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result["accessToken"],
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "development",
        max_age=settings.session_ttl_minutes * 60,
    )
    return ok(result)
