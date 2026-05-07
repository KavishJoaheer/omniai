"""M15 — Identity & Access tests.

Covers:
  1. TOTP MFA — setup, confirm, disable, recovery codes, login challenge
  2. User invitation flow — create, accept, list, revoke, expiry
  3. OIDC routes — authorize URL, invalid state, unknown provider
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

_ADMIN_EMAIL = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


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
    r = client.post("/v1/auth/login", json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["data"]["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. TOTP MFA
# ══════════════════════════════════════════════════════════════════════════════

class TestTOTPMFA:

    def _register_and_login(self, client, email: str, password: str = "ValidPass99!") -> str:
        """Register a fresh user and return their access token."""
        r = client.post("/v1/auth/register", json={
            "email": email, "password": password, "display_name": "MFA Tester"
        })
        if r.status_code in (200, 201):
            return r.json()["data"]["accessToken"]
        # Already exists — login
        r2 = client.post("/v1/auth/login", json={"email": email, "password": password})
        assert r2.status_code == 200, r2.text
        data = r2.json()["data"]
        assert "accessToken" in data, f"Unexpected: {data}"
        return data["accessToken"]

    def test_mfa_status_initially_false(self, client):
        token = self._register_and_login(client, "mfa_status@test.local")
        r = client.get("/v1/auth/mfa/status", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["data"]["mfaEnabled"] is False

    def test_mfa_setup_returns_secret_and_uri(self, client):
        token = self._register_and_login(client, "mfa_setup@test.local")
        r = client.post("/v1/auth/mfa/setup", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "secret" in data
        assert "provisioningUri" in data
        assert "otpauth://" in data["provisioningUri"]

    def test_mfa_confirm_with_valid_code(self, client):
        import pyotp
        token = self._register_and_login(client, "mfa_confirm@test.local")
        headers = {"Authorization": f"Bearer {token}"}

        setup_r = client.post("/v1/auth/mfa/setup", headers=headers)
        secret = setup_r.json()["data"]["secret"]

        totp = pyotp.TOTP(secret)
        confirm_r = client.post(
            "/v1/auth/mfa/confirm",
            json={"code": totp.now()},
            headers=headers,
        )
        assert confirm_r.status_code == 200
        data = confirm_r.json()["data"]
        assert data["mfaEnabled"] is True
        assert len(data["recoveryCodes"]) == 8

    def test_mfa_confirm_with_wrong_code_rejected(self, client):
        token = self._register_and_login(client, "mfa_badcode@test.local")
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/v1/auth/mfa/setup", headers=headers)
        r = client.post("/v1/auth/mfa/confirm", json={"code": "000000"}, headers=headers)
        assert r.status_code == 400

    def test_mfa_disable_with_valid_code(self, client):
        import pyotp
        token = self._register_and_login(client, "mfa_disable@test.local")
        headers = {"Authorization": f"Bearer {token}"}

        setup_r = client.post("/v1/auth/mfa/setup", headers=headers)
        secret = setup_r.json()["data"]["secret"]
        totp = pyotp.TOTP(secret)
        client.post("/v1/auth/mfa/confirm", json={"code": totp.now()}, headers=headers)

        disable_r = client.post("/v1/auth/mfa/disable", json={"code": totp.now()}, headers=headers)
        assert disable_r.status_code == 200
        assert disable_r.json()["data"]["mfaEnabled"] is False

    def test_login_returns_challenge_when_mfa_enabled(self, client):
        import pyotp
        email = "mfa_challenge@test.local"
        password = "ValidPass99!"
        token = self._register_and_login(client, email, password)
        headers = {"Authorization": f"Bearer {token}"}

        setup_r = client.post("/v1/auth/mfa/setup", headers=headers)
        secret = setup_r.json()["data"]["secret"]
        totp = pyotp.TOTP(secret)
        client.post("/v1/auth/mfa/confirm", json={"code": totp.now()}, headers=headers)

        login_r = client.post("/v1/auth/login", json={"email": email, "password": password})
        assert login_r.status_code == 200
        data = login_r.json()["data"]
        assert data.get("mfaRequired") is True
        assert "mfaChallengeToken" in data

    def test_mfa_verify_with_valid_code_issues_session(self, client):
        import pyotp
        email = "mfa_verify_flow@test.local"
        password = "ValidPass99!"
        token = self._register_and_login(client, email, password)
        headers = {"Authorization": f"Bearer {token}"}

        setup_r = client.post("/v1/auth/mfa/setup", headers=headers)
        secret = setup_r.json()["data"]["secret"]
        totp = pyotp.TOTP(secret)
        client.post("/v1/auth/mfa/confirm", json={"code": totp.now()}, headers=headers)

        login_r = client.post("/v1/auth/login", json={"email": email, "password": password})
        challenge_token = login_r.json()["data"]["mfaChallengeToken"]

        verify_r = client.post("/v1/auth/mfa/verify", json={
            "challenge_token": challenge_token,
            "code": totp.now(),
        })
        assert verify_r.status_code == 200
        assert "accessToken" in verify_r.json()["data"]

    def test_recovery_code_can_be_used_once(self, client, container):
        """Unit-level: verify a recovery code redeems once then is consumed."""
        import pyotp
        from omniai.application.auth_service import AuthService, RegisterInput
        from omniai.application.identity_service import IdentityService, MFAVerifyInput
        from omniai.adapters.relational.sqlalchemy.models import UserRecord
        from sqlalchemy import select

        email = "recovery_code@test.local"
        with container.database.new_session() as session:
            auth = AuthService(session, container.settings)
            try:
                auth.register(
                    RegisterInput(email=email, password="ValidPass99!", display_name="RC User"),
                    container.default_tenant_id,
                )
            except ValueError:
                pass
            from omniai.application.auth_service import AuthenticatedPrincipal
            user = session.scalar(select(UserRecord).where(UserRecord.email == email))
            principal = AuthenticatedPrincipal(
                user_id=user.id, email=email, display_name="RC User",
                tenant_id=container.default_tenant_id, tenant_name="t",
                role="MEMBER", auth_type="session",
            )
            id_svc = IdentityService(session, container.settings)
            id_svc.mfa_setup(principal)
            setup_code = pyotp.TOTP(user.totp_secret).now()
            result = id_svc.mfa_confirm(principal, MFAVerifyInput(code=setup_code))
            recovery_codes = result["recoveryCodes"]
            raw_code = recovery_codes[0]

            # First use: should succeed
            assert id_svc.verify_totp_or_recovery(user, raw_code) is True
            # Second use of same code: consumed, should fail
            assert id_svc.verify_totp_or_recovery(user, raw_code) is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. User invitation flow
# ══════════════════════════════════════════════════════════════════════════════

class TestInvitationFlow:

    def test_create_invitation_returns_token(self, client, auth_headers):
        r = client.post(
            "/v1/invitations",
            json={"email": "invite_test@example.com", "role": "MEMBER"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert "inviteToken" in data
        assert data["email"] == "invite_test@example.com"

    def test_list_invitations(self, client, auth_headers):
        client.post(
            "/v1/invitations",
            json={"email": "invite_list@example.com"},
            headers=auth_headers,
        )
        r = client.get("/v1/invitations", headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["data"]
        assert isinstance(items, list)
        assert len(items) >= 1

    def test_accept_invitation_creates_user(self, client, auth_headers):
        create_r = client.post(
            "/v1/invitations",
            json={"email": "invite_accept@example.com", "role": "MEMBER"},
            headers=auth_headers,
        )
        token = create_r.json()["data"]["inviteToken"]

        accept_r = client.post("/v1/invitations/accept", json={
            "token": token,
            "display_name": "New Member",
            "password": "AcceptPass99!",
        })
        assert accept_r.status_code == 200
        data = accept_r.json()["data"]
        assert data["email"] == "invite_accept@example.com"

    def test_accept_same_token_twice_fails(self, client, auth_headers):
        create_r = client.post(
            "/v1/invitations",
            json={"email": "invite_twice@example.com"},
            headers=auth_headers,
        )
        token = create_r.json()["data"]["inviteToken"]

        client.post("/v1/invitations/accept", json={
            "token": token, "display_name": "X", "password": "ValidPass99!"
        })
        r2 = client.post("/v1/invitations/accept", json={
            "token": token, "display_name": "X", "password": "ValidPass99!"
        })
        assert r2.status_code == 400

    def test_expired_invitation_rejected(self, client, container, auth_headers):
        from omniai.adapters.relational.sqlalchemy.models import InvitationRecord
        from sqlalchemy import select

        create_r = client.post(
            "/v1/invitations",
            json={"email": "invite_expired@example.com"},
            headers=auth_headers,
        )
        invite_id = create_r.json()["data"]["id"]
        token = create_r.json()["data"]["inviteToken"]

        # Manually expire the invitation
        with container.database.new_session() as session:
            inv = session.scalar(select(InvitationRecord).where(InvitationRecord.id == invite_id))
            inv.expires_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
            session.commit()

        r = client.post("/v1/invitations/accept", json={
            "token": token, "display_name": "X", "password": "ValidPass99!"
        })
        assert r.status_code == 400
        assert "expired" in r.json()["detail"].lower()

    def test_revoke_invitation(self, client, auth_headers):
        create_r = client.post(
            "/v1/invitations",
            json={"email": "invite_revoke@example.com"},
            headers=auth_headers,
        )
        invite_id = create_r.json()["data"]["id"]

        r = client.delete(f"/v1/invitations/{invite_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["revoked"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. OIDC routes (provider config validation only; real OAuth not testable)
# ══════════════════════════════════════════════════════════════════════════════

class TestOIDCRoutes:

    def test_authorize_unknown_provider_returns_400(self, client, auth_headers):
        r = client.get(
            "/v1/auth/oidc/notaProvider/authorize?redirect_uri=http://localhost",
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "unknown" in r.json()["detail"].lower() or "not configured" in r.json()["detail"].lower()

    def test_authorize_unconfigured_provider_returns_400(self, client, auth_headers):
        # google is a known preset but no CLIENT_ID is configured in tests
        r = client.get(
            "/v1/auth/oidc/google/authorize?redirect_uri=http://localhost:5173/callback",
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "not configured" in r.json()["detail"].lower()

    def test_callback_invalid_state_rejected(self, client):
        r = client.get(
            "/v1/auth/oidc/google/callback?code=fake&state=notavalidstate"
        )
        assert r.status_code == 401
