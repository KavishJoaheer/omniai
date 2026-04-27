from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.application.auth_service import AuthService, AuthenticatedPrincipal
from omniai.application.provider_service import ProviderActor, ProviderService
from omniai.application.services import KnowledgeService
from omniai.observability.metrics import MetricsRegistry
from omniai.security.secrets import SecretBox


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.container.database.new_session()
    try:
        yield session
    finally:
        session.close()


def get_secret_box(request: Request) -> SecretBox:
    return request.app.state.container.secret_box


def get_auth_service(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AuthService:
    return AuthService(session, request.app.state.container.settings)


def get_current_principal(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedPrincipal:
    settings = request.app.state.container.settings
    authorization = request.headers.get("Authorization")
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    try:
        if token.startswith("omsk_"):
            return auth_service.authenticate_api_key(token)
        return auth_service.authenticate_session_token(token)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_admin_principal(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    if principal.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return principal


def get_knowledge_service(
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> KnowledgeService:
    store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    return KnowledgeService(store)


def get_provider_service(
    session: Session = Depends(get_db_session),
    secret_box: SecretBox = Depends(get_secret_box),
    _: AuthenticatedPrincipal = Depends(get_current_principal),
) -> ProviderService:
    return ProviderService(session, secret_box)


def principal_to_provider_actor(principal: AuthenticatedPrincipal) -> ProviderActor:
    return ProviderActor(user_id=principal.user_id, tenant_id=principal.tenant_id, role=principal.role)


def get_metrics(request: Request) -> MetricsRegistry:
    return request.app.state.container.metrics
