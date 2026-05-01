from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyAgentStore, SqlAlchemyKnowledgeStore
from omniai.application.agent_service import AgentService
from omniai.application.auth_service import AuthService, AuthenticatedPrincipal
from omniai.application.chat_service import ChatService
from omniai.application.ingestion_service import IngestionService
from omniai.application.provider_service import ProviderActor, ProviderService
from omniai.application.retrieval_service import RetrievalService
from omniai.application.services import KnowledgeService
from omniai.observability.metrics import MetricsRegistry
from omniai.plugins.chunk_templates.registry import ChunkTemplateRegistry
from omniai.plugins.embedding_providers.factory import build_embedding_provider
from omniai.plugins.parsers import ParserRegistry
from omniai.ports.object_store import ObjectStorePort
from omniai.ports.queue import JobQueuePort
from omniai.ports.search_engine import SearchEnginePort
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
    return KnowledgeService(store, tenant_role=principal.role, user_id=principal.user_id)


def get_object_store(request: Request) -> ObjectStorePort:
    return request.app.state.container.object_store


def get_job_queue(request: Request) -> JobQueuePort:
    return request.app.state.container.job_queue


def get_parser_registry(request: Request) -> ParserRegistry:
    return request.app.state.container.parsers


def get_ingestion_service(
    request: Request,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    object_store: ObjectStorePort = Depends(get_object_store),
    queue: JobQueuePort = Depends(get_job_queue),
    parsers: ParserRegistry = Depends(get_parser_registry),
) -> IngestionService:
    store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    settings = request.app.state.container.settings
    return IngestionService(
        store=store,
        object_store=object_store,
        queue=queue,
        parsers=parsers,
        tenant_id=principal.tenant_id,
        max_bytes=settings.upload_max_bytes,
        tenant_max_documents=settings.tenant_max_documents,
        tenant_max_storage_bytes=settings.tenant_max_storage_bytes,
    )


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


def get_search_engine(request: Request) -> SearchEnginePort:
    return request.app.state.container.search_engine


def get_chunk_templates(request: Request) -> ChunkTemplateRegistry:
    return request.app.state.container.chunk_templates


def get_retrieval_service(
    request: Request,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    search_engine: SearchEnginePort = Depends(get_search_engine),
) -> RetrievalService:
    settings = request.app.state.container.settings
    provider, _ = build_embedding_provider(
        session=session,
        settings=settings,
        tenant_id=principal.tenant_id,
        requested_model="nomic-embed-text",
    )
    store = SqlAlchemyKnowledgeStore(session, principal.tenant_id)
    container = request.app.state.container
    return RetrievalService(
        search_engine=search_engine,
        embedding_provider=provider,
        tenant_id=principal.tenant_id,
        store=store,
        reranker=container.reranker,
        cache=container.retrieval_cache,
        cache_ttl=container.settings.retrieval_cache_ttl_seconds,
    )


def get_chat_service(
    request: Request,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    secret_box: SecretBox = Depends(get_secret_box),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> ChatService:
    return ChatService(
        session=session,
        settings=request.app.state.container.settings,
        secret_box=secret_box,
        retrieval_service=retrieval_service,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
    )


def get_agent_service(
    request: Request,
    session: Session = Depends(get_db_session),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> AgentService:
    settings = request.app.state.container.settings
    return AgentService(
        store=SqlAlchemyAgentStore(session, principal.tenant_id),
        retrieval_service=retrieval_service,
        sandbox=request.app.state.container.sandbox,
        cost_alert_usd=float(getattr(settings, "agent_run_cost_alert_usd", 0.0) or 0.0),
    )
