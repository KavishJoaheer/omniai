from fastapi import APIRouter, Depends

from omniai.application.auth_service import AuthService
from omniai.interfaces.http.deps import get_auth_service, require_admin_principal
from omniai.interfaces.http.envelope import ok

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/users")
def list_users(
    principal=Depends(require_admin_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.list_users(principal))


@router.get("/audit-events")
def list_audit_events(
    principal=Depends(require_admin_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return ok(auth_service.list_audit_events(principal))
