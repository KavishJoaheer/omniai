"""M14 — Production hardening tests.

Covers:
  1. Account lockout — failure counter, lock enforcement, auto-unlock after TTL
  2. Audit log pagination — cursor, limit, hasMore
  3. Security headers — presence + values on every response
  4. Distributed scheduler lock (_InProcessSyncLock) — mutual exclusion
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Test-env credentials (must match conftest.py) ──────────────────────────
_ADMIN_EMAIL = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Account lockout
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def app():
    from omniai.interfaces.http.app import create_app
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestAccountLockout:
    """Unit tests for AuthService lockout logic (no HTTP stack)."""

    def _make_service(self, container):
        from omniai.application.auth_service import AuthService
        session = container.database.new_session()
        return AuthService(session, container.settings), session

    def _register_test_user(self, container, email: str) -> None:
        from omniai.application.auth_service import AuthService, RegisterInput
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            try:
                svc.register(
                    RegisterInput(email=email, password="ValidPass99!", display_name="Test"),
                    container.default_tenant_id,
                )
            except ValueError:
                pass  # already exists — that's fine

    def test_failed_login_increments_counter(self, container):
        email = "locktest_counter@test.local"
        self._register_test_user(container, email)

        from omniai.application.auth_service import AuthService, LoginInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        session = container.database.new_session()
        svc = AuthService(session, container.settings)

        with pytest.raises(PermissionError, match="Invalid"):
            svc.login(LoginInput(email=email, password="WrongPass99!"))

        user = session.scalar(select(UserRecord).where(UserRecord.email == email))
        assert user is not None
        assert user.failed_login_attempts == 1
        session.close()

    def test_success_resets_counter(self, container):
        email = "locktest_reset@test.local"
        self._register_test_user(container, email)

        from omniai.application.auth_service import AuthService, LoginInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        session = container.database.new_session()
        svc = AuthService(session, container.settings)

        # One failure
        with pytest.raises(PermissionError):
            svc.login(LoginInput(email=email, password="WrongPass99!"))

        # Now succeed
        svc.login(LoginInput(email=email, password="ValidPass99!"))

        user = session.scalar(select(UserRecord).where(UserRecord.email == email))
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
        session.close()

    def test_account_locks_after_threshold(self, container):
        email = "locktest_lock@test.local"
        self._register_test_user(container, email)

        from omniai.application.auth_service import AuthService, LoginInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        threshold = container.settings.login_lockout_threshold
        session = container.database.new_session()
        svc = AuthService(session, container.settings)

        for _ in range(threshold):
            with pytest.raises(PermissionError):
                svc.login(LoginInput(email=email, password="WrongPass99!"))

        user = session.scalar(select(UserRecord).where(UserRecord.email == email))
        assert user.locked_until is not None
        # SQLite may return a naive datetime; normalise before comparing.
        locked_ts = user.locked_until
        if locked_ts.tzinfo is None:
            locked_ts = locked_ts.replace(tzinfo=timezone.utc)
        assert locked_ts > datetime.now(timezone.utc)
        session.close()

    def test_locked_account_rejects_correct_password(self, container):
        email = "locktest_correct@test.local"
        self._register_test_user(container, email)

        from omniai.application.auth_service import AuthService, LoginInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        threshold = container.settings.login_lockout_threshold
        session = container.database.new_session()
        svc = AuthService(session, container.settings)

        # Exhaust threshold
        for _ in range(threshold):
            with pytest.raises(PermissionError):
                svc.login(LoginInput(email=email, password="WrongPass99!"))

        # Even the correct password is rejected while locked
        with pytest.raises(PermissionError, match="locked"):
            svc.login(LoginInput(email=email, password="ValidPass99!"))
        session.close()

    def test_lock_expires_after_duration(self, container):
        """Simulate an expired lock by setting locked_until in the past."""
        email = "locktest_expire@test.local"
        self._register_test_user(container, email)

        from omniai.application.auth_service import AuthService, LoginInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        # Manually set locked_until to 1 second ago
        session = container.database.new_session()
        user = session.scalar(select(UserRecord).where(UserRecord.email == email))
        user.failed_login_attempts = 10
        user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

        svc = AuthService(session, container.settings)
        # Should succeed — lock has expired
        result = svc.login(LoginInput(email=email, password="ValidPass99!"))
        assert "accessToken" in result

        # Counter should be reset
        user = session.scalar(select(UserRecord).where(UserRecord.email == email))
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Audit log pagination
# ══════════════════════════════════════════════════════════════════════════════


class TestAuditLogPagination:

    def _seed_audit_events(self, container, count: int = 15) -> None:
        """Trigger <count> actions that produce audit events."""
        from omniai.application.auth_service import AuthService, RegisterInput
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            for i in range(count):
                try:
                    svc.register(
                        RegisterInput(
                            email=f"auditpag_{i}@test.local",
                            password="ValidPass99!",
                            display_name=f"User {i}",
                        ),
                        container.default_tenant_id,
                    )
                except (ValueError, Exception):
                    pass  # duplicates OK — just need events to exist

    def test_default_returns_dict_with_items(self, container):
        self._seed_audit_events(container)
        from omniai.application.auth_service import AuthService, AuthenticatedPrincipal

        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            result = svc.list_audit_events(
                AuthenticatedPrincipal(
                    user_id="dummy", email="x@x.com", display_name="x",
                    tenant_id=container.default_tenant_id, tenant_name="t",
                    role="OWNER", auth_type="session",
                ),
            )
        assert isinstance(result, dict)
        assert "items" in result
        assert "hasMore" in result
        assert "nextCursor" in result
        assert isinstance(result["items"], list)

    def test_limit_respected(self, container):
        from omniai.application.auth_service import AuthService, AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            user_id="dummy", email="x@x.com", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            result = svc.list_audit_events(principal, limit=3)
        assert len(result["items"]) <= 3

    def test_cursor_pagination_covers_all_events(self, container):
        """Walk all pages with limit=5 and assert total == single-page total."""
        from omniai.application.auth_service import AuthService, AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            user_id="dummy", email="x@x.com", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )
        # Collect all IDs in one big query
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            full = svc.list_audit_events(principal, limit=200)
        all_ids_one_shot = {e["id"] for e in full["items"]}

        # Now page through limit=5
        collected_ids: set[str] = set()
        cursor = None
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            for _ in range(100):  # safety cap
                page = svc.list_audit_events(principal, limit=5, before_id=cursor)
                for e in page["items"]:
                    collected_ids.add(e["id"])
                if not page["hasMore"]:
                    break
                cursor = page["nextCursor"]

        assert collected_ids == all_ids_one_shot

    def test_empty_before_id_is_ignored_gracefully(self, container):
        from omniai.application.auth_service import AuthService, AuthenticatedPrincipal

        principal = AuthenticatedPrincipal(
            user_id="dummy", email="x@x.com", display_name="x",
            tenant_id=container.default_tenant_id, tenant_name="t",
            role="OWNER", auth_type="session",
        )
        with container.database.new_session() as session:
            svc = AuthService(session, container.settings)
            # Non-existent before_id should just return first page
            result = svc.list_audit_events(principal, before_id="nonexistent_id_xyz")
        assert isinstance(result["items"], list)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Security headers middleware
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurityHeaders:
    """Ensure every response carries the security headers added in M14."""

    def test_xss_protection_headers_present(self, client):
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"

    def test_referrer_policy(self, client):
        r = client.get("/v1/health")
        assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        r = client.get("/v1/health")
        policy = r.headers.get("permissions-policy", "")
        assert "camera=()" in policy
        assert "microphone=()" in policy

    def test_csp_header_present(self, client):
        r = client.get("/v1/health")
        csp = r.headers.get("content-security-policy", "")
        assert "default-src" in csp
        assert "frame-ancestors" in csp

    def test_headers_on_authenticated_endpoint(self, client, auth_headers):
        r = client.get("/v1/admin/users", headers=auth_headers)
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"

    def test_headers_on_404(self, client):
        """Even 404 responses should carry security headers."""
        r = client.get("/v1/totally/nonexistent/path")
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_hsts_absent_in_test_env(self, client):
        """HSTS should NOT be set when APP_ENV != production (the test env)."""
        r = client.get("/v1/health")
        # Absent is fine; present with max-age=0 would also be fine.
        hsts = r.headers.get("strict-transport-security", "")
        # In test env APP_ENV is not "production", so HSTS must be absent.
        assert hsts == ""


# ══════════════════════════════════════════════════════════════════════════════
# 4. Distributed scheduler lock
# ══════════════════════════════════════════════════════════════════════════════


class TestInProcessSyncLock:
    """Unit tests for _InProcessSyncLock without a real scheduler."""

    def _make_lock(self):
        from omniai.application.connector_service import _InProcessSyncLock
        return _InProcessSyncLock()

    def test_acquire_yields_true_when_free(self):
        lock = self._make_lock()

        async def _run():
            async with lock.acquire("conn_1") as acquired:
                return acquired

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is True

    def test_acquire_yields_false_when_held(self):
        lock = self._make_lock()
        results: list[bool] = []

        async def _run():
            async with lock.acquire("conn_2") as outer:
                results.append(outer)
                # Try to acquire the same connector while the outer lock is held
                async with lock.acquire("conn_2") as inner:
                    results.append(inner)

        asyncio.get_event_loop().run_until_complete(_run())
        assert results == [True, False]

    def test_different_connectors_independent(self):
        lock = self._make_lock()

        async def _run():
            r1, r2 = False, False
            async with lock.acquire("conn_A") as a:
                r1 = a
                async with lock.acquire("conn_B") as b:
                    r2 = b
            return r1, r2

        r1, r2 = asyncio.get_event_loop().run_until_complete(_run())
        assert r1 is True
        assert r2 is True

    def test_lock_released_after_context(self):
        lock = self._make_lock()

        async def _run():
            async with lock.acquire("conn_3"):
                pass  # released here
            # Should be acquirable again
            async with lock.acquire("conn_3") as second:
                return second

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is True

    def test_lock_released_on_exception(self):
        lock = self._make_lock()

        async def _run():
            try:
                async with lock.acquire("conn_4"):
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            # Should still be acquirable after the exception
            async with lock.acquire("conn_4") as acq:
                return acq

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# 5. Admin audit-events HTTP endpoint pagination
# ══════════════════════════════════════════════════════════════════════════════


class TestAuditEventRoute:

    def test_route_returns_paginated_envelope(self, client, auth_headers):
        r = client.get("/v1/admin/audit-events?limit=5", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data
        assert "hasMore" in data
        assert "nextCursor" in data

    def test_limit_param_rejected_when_too_large(self, client, auth_headers):
        r = client.get("/v1/admin/audit-events?limit=999", headers=auth_headers)
        # FastAPI's Query(le=200) should reject this with 422
        assert r.status_code == 422

    def test_limit_param_rejected_when_zero(self, client, auth_headers):
        r = client.get("/v1/admin/audit-events?limit=0", headers=auth_headers)
        assert r.status_code == 422

    def test_pagination_cursor_accepted(self, client, auth_headers):
        # Page 1
        r1 = client.get("/v1/admin/audit-events?limit=2", headers=auth_headers)
        data1 = r1.json()["data"]
        cursor = data1.get("nextCursor")
        if cursor:
            r2 = client.get(
                f"/v1/admin/audit-events?limit=2&before_id={cursor}",
                headers=auth_headers,
            )
            assert r2.status_code == 200
            data2 = r2.json()["data"]
            # The two pages must have distinct IDs
            ids1 = {e["id"] for e in data1["items"]}
            ids2 = {e["id"] for e in data2["items"]}
            assert ids1.isdisjoint(ids2), "Pages must not overlap"
