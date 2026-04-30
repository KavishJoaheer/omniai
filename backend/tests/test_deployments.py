"""Deploy Manager — unit + integration tests.

Coverage:
  - Slug validation (valid / invalid / reserved)
  - DeploymentService.assert_active (raises when PAUSED)
  - DeploymentService.assert_within_daily_quota (raises at cap, resets on new day)
  - Full CRUD round-trip via SqlAlchemyDeploymentStore
  - Slug global-uniqueness guard
  - DeploymentBySlugLookup.find returns None for unknown slug
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from omniai.application.deployment_service import (
    DeploymentQuotaExceeded,
    DeploymentService,
    validate_slug,
)
from omniai.domain.deployments.models import Deployment


# ---- pure slug validation ---------------------------------------------------


def test_valid_slug_passes():
    validate_slug("my-chatbot")  # no exception


def test_slug_too_short_raises():
    with pytest.raises(ValueError, match="Slug must be"):
        validate_slug("ab")


def test_slug_with_uppercase_raises():
    with pytest.raises(ValueError, match="Slug must be"):
        validate_slug("My-Bot")


def test_slug_with_spaces_raises():
    with pytest.raises(ValueError, match="Slug must be"):
        validate_slug("my bot")


def test_reserved_slug_raises():
    with pytest.raises(ValueError, match="reserved"):
        validate_slug("admin")


def test_reserved_slug_auth_raises():
    # "auth" is 4 chars and reserved — hits the reserved check, not the regex check
    with pytest.raises(ValueError, match="reserved"):
        validate_slug("auth")


# ---- assert_active ----------------------------------------------------------


def _make_deployment(**overrides) -> Deployment:
    defaults = dict(
        name="Test",
        slug="test-dep",
        target_id="col_abc",
        target_kind="collection",
        status="ACTIVE",
    )
    defaults.update(overrides)
    return Deployment(**defaults)


def test_assert_active_passes_for_active_deployment():
    DeploymentService.assert_active(_make_deployment(status="ACTIVE"))  # no exception


def test_assert_active_raises_for_paused():
    dep = _make_deployment(status="PAUSED")
    with pytest.raises(DeploymentQuotaExceeded, match="paused"):
        DeploymentService.assert_active(dep)


# ---- assert_within_daily_quota ----------------------------------------------


def test_quota_unlimited_when_zero():
    """daily_message_quota=0 means no cap."""
    dep = _make_deployment(
        daily_message_quota=0,
        today_message_count=99999,
        today_window_start=datetime.now(timezone.utc),
    )
    DeploymentService.assert_within_daily_quota(dep)  # no exception


def test_quota_not_exceeded_under_cap():
    dep = _make_deployment(
        daily_message_quota=10,
        today_message_count=5,
        today_window_start=datetime.now(timezone.utc),
    )
    DeploymentService.assert_within_daily_quota(dep)  # no exception


def test_quota_raises_when_at_cap():
    dep = _make_deployment(
        daily_message_quota=10,
        today_message_count=10,
        today_window_start=datetime.now(timezone.utc),
    )
    with pytest.raises(DeploymentQuotaExceeded, match="quota"):
        DeploymentService.assert_within_daily_quota(dep)


def test_quota_resets_for_new_day():
    """today_window_start on a previous date → counts as 0 for today."""
    from datetime import timedelta

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    dep = _make_deployment(
        daily_message_quota=5,
        today_message_count=99,  # would violate cap if window counted
        today_window_start=yesterday,
    )
    # Should NOT raise — window is stale, so treated as 0 for today
    DeploymentService.assert_within_daily_quota(dep)


# ---- CRUD round-trip via store + service ------------------------------------


@pytest.fixture
def deploy_session(container):
    """A fresh session for deployment CRUD tests."""
    session = container.database.new_session()
    yield session
    session.close()


@pytest.fixture
def deploy_service(deploy_session, tenant_id):
    from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyDeploymentStore

    store = SqlAlchemyDeploymentStore(deploy_session, tenant_id)
    return DeploymentService(store=store, tenant_id=tenant_id)


def _make_target(deploy_session, tenant_id) -> str:
    """Create a collection and return its ID to use as target_id."""
    import uuid
    from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore

    store = SqlAlchemyKnowledgeStore(deploy_session, tenant_id)
    col = store.create_collection(
        name=f"Deploy Target {uuid.uuid4().hex[:6]}",
        description=None,
        embedding_model="nomic-embed-text",
        chunk_template="general",
    )
    return col.id


def test_create_and_get_deployment(deploy_service, deploy_session, tenant_id):
    target_id = _make_target(deploy_session, tenant_id)
    dep = deploy_service.create(
        name="Integration Chat",
        slug="integration-chat",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    assert dep.id.startswith("dep_")
    assert dep.slug == "integration-chat"
    assert dep.status == "ACTIVE"
    assert dep.daily_message_quota == 500  # default

    fetched = deploy_service.get(dep.id)
    assert fetched.name == "Integration Chat"


def test_list_deployments(deploy_service, deploy_session, tenant_id):
    target_id = _make_target(deploy_session, tenant_id)
    deploy_service.create(
        name="List Chat Alpha",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    deploy_service.create(
        name="List Chat Beta",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    names = {d.name for d in deploy_service.list()}
    assert "List Chat Alpha" in names
    assert "List Chat Beta" in names


def test_pause_and_resume_deployment(deploy_service, deploy_session, tenant_id):
    target_id = _make_target(deploy_session, tenant_id)
    dep = deploy_service.create(
        name="Pause Resume Chat",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    paused = deploy_service.pause(dep.id)
    assert paused.status == "PAUSED"

    resumed = deploy_service.resume(dep.id)
    assert resumed.status == "ACTIVE"


def test_delete_deployment_hides_from_list(deploy_service, deploy_session, tenant_id):
    target_id = _make_target(deploy_session, tenant_id)
    dep = deploy_service.create(
        name="Delete Me Chat",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    deploy_service.delete(dep.id)
    ids = {d.id for d in deploy_service.list()}
    assert dep.id not in ids


def test_slug_uniqueness_across_tenants(deploy_service, deploy_session, tenant_id):
    """Two deployments with the same slug must fail with ValueError."""
    target_id = _make_target(deploy_session, tenant_id)
    deploy_service.create(
        name="Slug Unique A",
        slug="unique-slug-test",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    with pytest.raises(ValueError, match="Slug"):
        deploy_service.create(
            name="Slug Unique B",
            slug="unique-slug-test",
            kind="public_chat",
            target_kind="collection",
            target_id=target_id,
        )


def test_unknown_slug_returns_404(deploy_session):
    """DeploymentBySlugLookup.find returns None for non-existent slug."""
    from omniai.adapters.relational.sqlalchemy.repositories import DeploymentBySlugLookup

    lookup = DeploymentBySlugLookup(deploy_session)
    result = lookup.find("this-slug-does-not-exist-xyz")
    assert result is None


def test_auto_slug_generated_when_not_provided(deploy_service, deploy_session, tenant_id):
    target_id = _make_target(deploy_session, tenant_id)
    dep = deploy_service.create(
        name="Auto Slug Example",
        kind="public_chat",
        target_kind="collection",
        target_id=target_id,
    )
    assert dep.slug.startswith("auto-slug-example")
    assert len(dep.slug) >= 3
