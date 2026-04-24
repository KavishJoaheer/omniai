from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.application.auth_service import AuthService, AuthenticatedPrincipal
from omniai.application.services import KnowledgeService
from omniai.observability.metrics import MetricsRegistry


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.database.new_session()
    try:
        yield session
    finally:
        session.close()


def get_auth_service(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AuthService:
    return AuthService(session, request.app.state.settings)


def get_current_principal(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedPrincipal:
    authorization = request.headers.get("Authorization")
    token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get(request.app.state.settings.session_cookie_name)
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
    request: Request,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> KnowledgeService:
    store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    return KnowledgeService(store)


def get_metrics(request: Request) -> MetricsRegistry:
    return request.app.state.metrics
