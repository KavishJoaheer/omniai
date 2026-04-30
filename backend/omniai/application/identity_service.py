"""M15 — Identity & Access service.

Covers three areas:
  1. TOTP-based MFA (pyotp) — enable, verify, disable, recovery codes
  2. User invitation flow — create invite link, accept, list, revoke
  3. OIDC SSO — build authorization URL, handle callback, upsert user

Each method receives a fully-authenticated principal so authorisation checks
are explicit.  All DB mutations go through the SQLAlchemy session passed in
at construction time.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    InvitationRecord,
    OIDCStateRecord,
    TenantMembershipRecord,
    UserRecord,
    generate_prefixed_id,
)
from omniai.application.auth_service import AuthenticatedPrincipal
from omniai.config.settings import Settings
from omniai.domain.knowledge.models import utc_now
from omniai.security.hashing import hash_password, verify_password
from omniai.security.permissions import Perm, assert_permission

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

class MFAVerifyInput(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class InviteCreateInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="MEMBER")


class InviteAcceptInput(BaseModel):
    token: str = Field(min_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


# ---------------------------------------------------------------------------
# OIDC provider registry
# ---------------------------------------------------------------------------

_OIDC_PRESETS: dict[str, dict[str, str]] = {
    "google": {
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": "openid email profile",
    },
    "github": {
        "authorization_endpoint": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_endpoint": "https://api.github.com/user",
        "scopes": "read:user user:email",
    },
    "microsoft": {
        "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
        "scopes": "openid email profile",
    },
}

# ---------------------------------------------------------------------------
# Number of TOTP recovery codes issued at enrollment
# ---------------------------------------------------------------------------
_RECOVERY_CODE_COUNT = 8
_RECOVERY_CODE_LEN = 10  # characters per code (alphanumeric, displayed as XXXXX-XXXXX)


class IdentityService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ══════════════════════════════════════════════════════════════════════
    # MFA — TOTP
    # ══════════════════════════════════════════════════════════════════════

    def mfa_setup(self, principal: AuthenticatedPrincipal) -> dict:
        """Generate a new TOTP secret and return the provisioning URI.

        The secret is written to the DB but MFA is NOT yet enforced — the
        user must call ``mfa_confirm`` with a valid code to activate it.
        """
        user = self._get_user(principal.user_id)
        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.mfa_enabled = 0  # confirmed only after verify
        self._session.commit()

        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=self._settings.app_name,
        )
        return {
            "secret": secret,
            "provisioningUri": provisioning_uri,
            "qrCodeUrl": f"https://chart.googleapis.com/chart?chs=200x200&chld=M|0&cht=qr&chl={urllib.parse.quote(provisioning_uri)}",
        }

    def mfa_confirm(self, principal: AuthenticatedPrincipal, payload: MFAVerifyInput) -> dict:
        """Verify the first TOTP code and activate MFA.  Returns recovery codes."""
        user = self._get_user(principal.user_id)
        if not user.totp_secret:
            raise ValueError("MFA setup not started. Call /mfa/setup first.")
        if bool(user.mfa_enabled):
            raise ValueError("MFA is already active.")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(payload.code, valid_window=1):
            raise PermissionError("Invalid TOTP code.")

        raw_codes, hashed_codes = self._generate_recovery_codes()
        user.mfa_enabled = 1
        user.mfa_recovery_codes_json = json.dumps(hashed_codes)
        self._session.commit()

        return {
            "mfaEnabled": True,
            "recoveryCodes": raw_codes,  # shown ONCE; user must store them
        }

    def mfa_disable(self, principal: AuthenticatedPrincipal, payload: MFAVerifyInput) -> dict:
        """Deactivate MFA after verifying the current code."""
        user = self._get_user(principal.user_id)
        if not bool(user.mfa_enabled) or not user.totp_secret:
            raise ValueError("MFA is not active.")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(payload.code, valid_window=1):
            raise PermissionError("Invalid TOTP code.")

        user.mfa_enabled = 0
        user.totp_secret = None
        user.mfa_recovery_codes_json = None
        self._session.commit()
        return {"mfaEnabled": False}

    def mfa_status(self, principal: AuthenticatedPrincipal) -> dict:
        user = self._get_user(principal.user_id)
        return {"mfaEnabled": bool(user.mfa_enabled)}

    def verify_totp_or_recovery(self, user: UserRecord, code: str) -> bool:
        """Return True if the code is a valid TOTP code *or* a valid recovery code.

        Recovery codes are single-use: a matched code is removed from the list.
        """
        if not bool(user.mfa_enabled) or not user.totp_secret:
            return False

        # Try TOTP first
        totp = pyotp.TOTP(user.totp_secret)
        if totp.verify(code.strip(), valid_window=1):
            return True

        # Try recovery codes
        if user.mfa_recovery_codes_json:
            stored: list[str] = json.loads(user.mfa_recovery_codes_json)
            normalised = code.strip().replace("-", "").upper()
            for i, hashed in enumerate(stored):
                if self._check_recovery_code(normalised, hashed):
                    # Consume it — one-time use
                    stored.pop(i)
                    user.mfa_recovery_codes_json = json.dumps(stored)
                    self._session.commit()
                    return True
        return False

    # ══════════════════════════════════════════════════════════════════════
    # Invitation flow
    # ══════════════════════════════════════════════════════════════════════

    def create_invitation(
        self,
        principal: AuthenticatedPrincipal,
        payload: InviteCreateInput,
    ) -> dict:
        assert_permission(principal.role, Perm.USERS_READ)
        email = payload.email.strip().lower()

        # Guard: don't invite an already-registered member
        existing = self._session.scalar(
            select(UserRecord).where(UserRecord.email == email)
        )
        if existing is not None:
            # Check if they're already in this tenant
            membership = self._session.scalar(
                select(TenantMembershipRecord).where(
                    TenantMembershipRecord.user_id == existing.id,
                    TenantMembershipRecord.tenant_id == principal.tenant_id,
                )
            )
            if membership is not None:
                raise ValueError("That user is already a member of this tenant.")

        raw_token = secrets.token_urlsafe(32)
        token_hash = self._hash_invite_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self._settings.invitation_expiry_hours
        )

        invite = InvitationRecord(
            tenant_id=principal.tenant_id,
            invited_by_user_id=principal.user_id,
            email=email,
            role=payload.role,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=utc_now(),
        )
        self._session.add(invite)
        self._session.commit()

        return {
            "id": invite.id,
            "email": invite.email,
            "role": invite.role,
            "expiresAt": invite.expires_at.isoformat(),
            # In production: deliver via email.  Returned here for dev convenience.
            "inviteToken": raw_token,
            "inviteUrl": f"/accept-invite?token={raw_token}",
        }

    def accept_invitation(self, token: str, payload: InviteAcceptInput) -> dict:
        """Validate an invite token and create the user + tenant membership."""
        token_hash = self._hash_invite_token(token)
        invite = self._session.scalar(
            select(InvitationRecord).where(InvitationRecord.token_hash == token_hash)
        )
        if invite is None:
            raise ValueError("Invitation not found or already used.")
        if invite.accepted_at is not None:
            raise ValueError("This invitation has already been accepted.")

        now = datetime.now(timezone.utc)
        expires_ts = invite.expires_at
        if expires_ts.tzinfo is None:
            expires_ts = expires_ts.replace(tzinfo=timezone.utc)
        if expires_ts < now:
            raise ValueError("This invitation has expired.")

        # Create or locate the user
        email = invite.email
        user = self._session.scalar(select(UserRecord).where(UserRecord.email == email))
        if user is None:
            user = UserRecord(
                primary_tenant_id=invite.tenant_id,
                email=email,
                display_name=payload.display_name.strip(),
                password_hash=hash_password(payload.password),
                is_active=1,
            )
            self._session.add(user)
            self._session.flush()

        # Add to tenant
        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user.id,
                TenantMembershipRecord.tenant_id == invite.tenant_id,
            )
        )
        if membership is None:
            self._session.add(
                TenantMembershipRecord(
                    tenant_id=invite.tenant_id,
                    user_id=user.id,
                    role=invite.role,
                )
            )

        invite.accepted_at = now
        self._session.commit()
        return {"userId": user.id, "email": user.email, "role": invite.role}

    def list_invitations(self, principal: AuthenticatedPrincipal) -> list[dict]:
        assert_permission(principal.role, Perm.USERS_READ)
        rows = self._session.scalars(
            select(InvitationRecord)
            .where(InvitationRecord.tenant_id == principal.tenant_id)
            .order_by(InvitationRecord.created_at.desc())
        )
        now = datetime.now(timezone.utc)
        result = []
        for inv in rows:
            expires_ts = inv.expires_at
            if expires_ts.tzinfo is None:
                expires_ts = expires_ts.replace(tzinfo=timezone.utc)
            result.append({
                "id": inv.id,
                "email": inv.email,
                "role": inv.role,
                "status": (
                    "accepted" if inv.accepted_at
                    else "expired" if expires_ts < now
                    else "pending"
                ),
                "expiresAt": inv.expires_at.isoformat(),
                "acceptedAt": inv.accepted_at.isoformat() if inv.accepted_at else None,
            })
        return result

    def revoke_invitation(self, principal: AuthenticatedPrincipal, invite_id: str) -> dict:
        assert_permission(principal.role, Perm.USERS_READ)
        invite = self._session.scalar(
            select(InvitationRecord).where(
                InvitationRecord.id == invite_id,
                InvitationRecord.tenant_id == principal.tenant_id,
            )
        )
        if invite is None:
            raise KeyError("Invitation not found.")
        if invite.accepted_at is not None:
            raise ValueError("Cannot revoke an accepted invitation.")
        # Mark as expired (set expires_at to epoch)
        invite.expires_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
        self._session.commit()
        return {"id": invite.id, "revoked": True}

    # ══════════════════════════════════════════════════════════════════════
    # OIDC / Social login
    # ══════════════════════════════════════════════════════════════════════

    def oidc_authorization_url(
        self,
        provider: str,
        redirect_uri: str,
    ) -> dict:
        """Build the authorization URL + CSRF state nonce for a given provider."""
        preset = _OIDC_PRESETS.get(provider.lower())
        if preset is None:
            raise ValueError(
                f"Unknown OIDC provider {provider!r}. "
                f"Supported: {', '.join(_OIDC_PRESETS)}"
            )
        client_id = self._settings.oidc_client_id(provider)
        if not client_id:
            raise ValueError(
                f"OIDC provider {provider!r} is not configured. "
                f"Set {provider.upper()}_CLIENT_ID in the environment."
            )

        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        self._session.add(
            OIDCStateRecord(
                state=state,
                provider=provider.lower(),
                redirect_uri=redirect_uri,
                expires_at=expires_at,
            )
        )
        self._session.commit()

        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": preset["scopes"],
            "state": state,
        }
        auth_url = preset["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
        return {"authorizationUrl": auth_url, "state": state}

    def oidc_callback(
        self,
        provider: str,
        code: str,
        state: str,
        tenant_id: str,
    ) -> dict:
        """Exchange authorization code for tokens, upsert user, return session."""
        import httpx

        # Validate CSRF state
        state_record = self._session.scalar(
            select(OIDCStateRecord).where(OIDCStateRecord.state == state)
        )
        if state_record is None:
            raise PermissionError("Invalid or expired OIDC state.")
        now = datetime.now(timezone.utc)
        expires_ts = state_record.expires_at
        if expires_ts.tzinfo is None:
            expires_ts = expires_ts.replace(tzinfo=timezone.utc)
        if expires_ts < now:
            raise PermissionError("OIDC state has expired.")
        # Consume the nonce
        self._session.delete(state_record)

        preset = _OIDC_PRESETS[provider.lower()]
        client_id = self._settings.oidc_client_id(provider)
        client_secret = self._settings.oidc_client_secret(provider)
        redirect_uri = state_record.redirect_uri or ""

        # Exchange code for access token
        token_resp = httpx.post(
            preset["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("No access token in OIDC response.")

        # Fetch user info
        userinfo_resp = httpx.get(
            preset["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        userinfo: dict[str, Any] = userinfo_resp.json()

        email = (userinfo.get("email") or "").strip().lower()
        if not email:
            # GitHub may need a separate email fetch
            if provider.lower() == "github":
                emails_resp = httpx.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                    timeout=10,
                )
                emails_resp.raise_for_status()
                for entry in emails_resp.json():
                    if entry.get("primary") and entry.get("verified"):
                        email = entry["email"].strip().lower()
                        break
        if not email:
            raise ValueError("Could not retrieve email from OIDC provider.")

        display_name = (
            userinfo.get("name")
            or userinfo.get("login")
            or email.split("@")[0]
        )

        # Upsert user
        user = self._session.scalar(select(UserRecord).where(UserRecord.email == email))
        if user is None:
            user = UserRecord(
                primary_tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                password_hash=hash_password(secrets.token_urlsafe(32)),  # random, SSO-only
                is_active=1,
            )
            self._session.add(user)
            self._session.flush()
            self._session.add(
                TenantMembershipRecord(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role="MEMBER",
                )
            )

        self._session.commit()

        # Issue a session token via AuthService
        from omniai.application.auth_service import AuthService
        auth_svc = AuthService(self._session, self._settings)
        from omniai.adapters.relational.sqlalchemy.models import TenantRecord
        tenant = self._session.scalar(select(TenantRecord).where(TenantRecord.id == tenant_id))
        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user.id,
                TenantMembershipRecord.tenant_id == tenant_id,
            )
        )
        if tenant is None or membership is None:
            raise PermissionError("OIDC user has no tenant access.")

        principal = auth_svc._build_principal(user, tenant, membership.role, auth_type="oidc")
        token = auth_svc.issue_session_token(principal)
        return auth_svc._build_auth_result(principal, token)

    # ══════════════════════════════════════════════════════════════════════
    # Internal helpers
    # ══════════════════════════════════════════════════════════════════════

    def _get_user(self, user_id: str) -> UserRecord:
        user = self._session.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if user is None:
            raise KeyError("User not found.")
        return user

    @staticmethod
    def _hash_invite_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _generate_recovery_codes() -> tuple[list[str], list[str]]:
        """Return (raw_codes, hashed_codes).  raw_codes shown once; hashes stored."""
        raw, hashed = [], []
        for _ in range(_RECOVERY_CODE_COUNT):
            code = secrets.token_hex(_RECOVERY_CODE_LEN // 2).upper()
            # Format as XXXXX-XXXXX for readability
            formatted = f"{code[:5]}-{code[5:]}"
            raw.append(formatted)
            hashed.append(
                hashlib.sha256(code.encode()).hexdigest()
            )
        return raw, hashed

    @staticmethod
    def _check_recovery_code(normalised: str, stored_hash: str) -> bool:
        return hashlib.sha256(normalised.encode()).hexdigest() == stored_hash
