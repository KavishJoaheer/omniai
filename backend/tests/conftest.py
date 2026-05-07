from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _set_test_env() -> Iterator[None]:
    """Configure environment for fast, hermetic, in-process tests."""
    tmp_storage = tempfile.mkdtemp(prefix="omniai-test-storage-")
    os.environ.setdefault("DB_URL", "sqlite:///:memory:")
    os.environ["DB_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
    os.environ["AUTO_CREATE_SCHEMA"] = "true"
    os.environ["OBJECT_STORE_KIND"] = "local"
    os.environ["OBJECT_STORE_LOCAL_DIR"] = tmp_storage
    os.environ["SEARCH_KIND"] = "memory"
    os.environ["WORKER_INLINE"] = "true"
    os.environ["ENCRYPTION_KEY"] = "a" * 40
    os.environ["AUTH_SECRET"] = "test-auth-secret"
    os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "test@local.dev"
    os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "TestPassword123!"
    os.environ["RERANKER_KIND"] = "paired"  # avoid heavy cross-encoder load in tests
    os.environ["SANDBOX_KIND"] = "subprocess"  # enable code-execution endpoints in tests
    os.environ["TENANT_MAX_DOCUMENTS"] = "100"
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"  # don't trip in tests
    # clear settings cache so the new env is read
    from omniai.config import settings as settings_module

    settings_module.get_settings.cache_clear()
    yield


@pytest.fixture
def container():
    from omniai.bootstrap.container import build_container
    from omniai.config.settings import get_settings

    return build_container(get_settings())


@pytest.fixture
def tenant_id(container):
    return container.default_tenant_id


@pytest.fixture
def store(container, tenant_id):
    """Yields a fresh KnowledgeStore bound to a fresh session."""
    from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore

    session = container.database.new_session()
    try:
        yield SqlAlchemyKnowledgeStore(session, tenant_id)
    finally:
        session.close()
