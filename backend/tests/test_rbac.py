"""Per-collection RBAC enforcement tests.

We exercise KnowledgeService directly with different (tenant_role, user_id)
contexts and verify that:
  - Tenant OWNER/ADMIN see and can mutate every collection (bypass)
  - Tenant MEMBER/VIEWER only see collections they're a member of
  - Membership upsert/remove respect the OWNER-required guard
  - Document operations also check collection-level access
"""
from __future__ import annotations

import pytest

from omniai.adapters.relational.sqlalchemy.repositories import SqlAlchemyKnowledgeStore
from omniai.application.services import (
    CreateCollectionInput,
    KnowledgeService,
    collection_role_meets,
    role_grants_collection_access,
)


# ---- pure helpers ---------------------------------------------------------


def test_role_grants_collection_access_for_tenant_admin():
    assert role_grants_collection_access(tenant_role="OWNER", required="VIEWER")
    assert role_grants_collection_access(tenant_role="ADMIN", required="EDITOR")
    assert not role_grants_collection_access(tenant_role="MEMBER", required="VIEWER")
    assert not role_grants_collection_access(tenant_role="VIEWER", required="VIEWER")


def test_collection_role_meets_ranking():
    assert collection_role_meets("OWNER", required="VIEWER")
    assert collection_role_meets("OWNER", required="EDITOR")
    assert collection_role_meets("OWNER", required="OWNER")
    assert collection_role_meets("EDITOR", required="EDITOR")
    assert collection_role_meets("EDITOR", required="VIEWER")
    assert not collection_role_meets("EDITOR", required="OWNER")
    assert collection_role_meets("VIEWER", required="VIEWER")
    assert not collection_role_meets("VIEWER", required="EDITOR")
    assert not collection_role_meets(None, required="VIEWER")


# ---- service-level enforcement --------------------------------------------


@pytest.fixture
def admin_service(container, tenant_id):
    """A service for a tenant OWNER (bypasses membership)."""
    session = container.database.new_session()
    store = SqlAlchemyKnowledgeStore(session, tenant_id)
    yield KnowledgeService(store, tenant_role="OWNER", user_id="usr_admin_test")
    session.close()


@pytest.fixture
def member_service(container, tenant_id):
    """A service for a non-admin tenant MEMBER."""
    session = container.database.new_session()
    store = SqlAlchemyKnowledgeStore(session, tenant_id)
    yield KnowledgeService(store, tenant_role="MEMBER", user_id="usr_member_test")
    session.close()


@pytest.fixture
def other_member_service(container, tenant_id):
    session = container.database.new_session()
    store = SqlAlchemyKnowledgeStore(session, tenant_id)
    yield KnowledgeService(store, tenant_role="MEMBER", user_id="usr_other_test")
    session.close()


def test_admin_sees_all_collections(admin_service):
    admin_service.create_collection(
        CreateCollectionInput(name="RBAC Admin Visibility", chunk_template="general")
    )
    visible = admin_service.list_collections()
    assert any(c.name == "RBAC Admin Visibility" for c in visible)


def test_member_only_sees_their_collections(admin_service, member_service):
    """Admin creates two collections; member sees neither."""
    a = admin_service.create_collection(
        CreateCollectionInput(name="RBAC Hidden A", chunk_template="general")
    )
    admin_service.create_collection(
        CreateCollectionInput(name="RBAC Hidden B", chunk_template="general")
    )
    visible_to_member = {c.id for c in member_service.list_collections()}
    assert a.id not in visible_to_member


def test_member_sees_collection_after_being_added(admin_service, member_service):
    col = admin_service.create_collection(
        CreateCollectionInput(name="RBAC Shared C", chunk_template="general")
    )
    admin_service.upsert_collection_member(
        collection_id=col.id, user_id="usr_member_test", role="VIEWER"
    )
    visible = {c.id for c in member_service.list_collections()}
    assert col.id in visible


def test_member_creating_collection_becomes_owner(member_service):
    col = member_service.create_collection(
        CreateCollectionInput(name="Member-owned RBAC D", chunk_template="general")
    )
    # Even a non-admin member must see their own creation
    visible = {c.id for c in member_service.list_collections()}
    assert col.id in visible
    # And they must hold OWNER role on it
    members = member_service.list_collection_members(col.id)
    roles = {m.user_id: m.role for m in members}
    assert roles.get("usr_member_test") == "OWNER"


def test_viewer_cannot_upsert_membership(admin_service, member_service):
    col = admin_service.create_collection(
        CreateCollectionInput(name="RBAC ViewerNoUpsert E", chunk_template="general")
    )
    admin_service.upsert_collection_member(
        collection_id=col.id, user_id="usr_member_test", role="VIEWER"
    )
    # As a VIEWER, member cannot add other members
    with pytest.raises(KeyError):
        member_service.upsert_collection_member(
            collection_id=col.id, user_id="usr_other_test", role="VIEWER"
        )


def test_member_cannot_see_other_members_collection(admin_service, other_member_service):
    """A member who's NOT in the collection must not see it OR its members."""
    col = admin_service.create_collection(
        CreateCollectionInput(name="RBAC Isolation F", chunk_template="general")
    )
    with pytest.raises(KeyError):
        other_member_service.get_collection(col.id)
    with pytest.raises(KeyError):
        other_member_service.list_collection_members(col.id)


def test_remove_collection_member_drops_visibility(admin_service, member_service):
    col = admin_service.create_collection(
        CreateCollectionInput(name="RBAC Removed G", chunk_template="general")
    )
    admin_service.upsert_collection_member(
        collection_id=col.id, user_id="usr_member_test", role="VIEWER"
    )
    assert col.id in {c.id for c in member_service.list_collections()}
    admin_service.remove_collection_member(
        collection_id=col.id, user_id="usr_member_test"
    )
    assert col.id not in {c.id for c in member_service.list_collections()}


def test_collection_delete_cascades_memberships(admin_service, container, tenant_id):
    col = admin_service.create_collection(
        CreateCollectionInput(name="RBAC Cascade H", chunk_template="general")
    )
    admin_service.upsert_collection_member(
        collection_id=col.id, user_id="usr_some_user", role="VIEWER"
    )
    # Sanity: membership exists
    assert any(
        m.user_id == "usr_some_user" for m in admin_service.list_collection_members(col.id)
    )
    # Now delete via the store directly (mirrors what IngestionService.delete_collection does)
    session = container.database.new_session()
    try:
        store = SqlAlchemyKnowledgeStore(session, tenant_id)
        store.delete_collection(collection_id=col.id)
        # Membership should be gone too
        from omniai.adapters.relational.sqlalchemy.models import CollectionMembershipRecord
        from sqlalchemy import select

        rows = list(
            session.scalars(
                select(CollectionMembershipRecord).where(
                    CollectionMembershipRecord.collection_id == col.id
                )
            )
        )
        assert rows == []
    finally:
        session.close()
