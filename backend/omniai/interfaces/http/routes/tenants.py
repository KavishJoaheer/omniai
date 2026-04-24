from fastapi import APIRouter, Depends

from omniai.application.auth_service import AuthService
from omniai.interfaces.http.deps import get_auth_service, get_current_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/tenants", tags=["tenants"])


@router.get("/current")
def current_tenant(
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.get_current_tenant(principal))


@router.get("/memberships")
def list_memberships(
    principal=Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.list_my_memberships(principal))
