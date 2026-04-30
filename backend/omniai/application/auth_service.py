from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from omniai.adapters.relational.sqlalchemy.models import (
    ApiKeyRecord,
    AuditEventRecord,
    RevokedTokenRecord,
    TeamMembershipRecord,
    TeamRecord,
    TenantMembershipRecord,
    TenantRecord,
    UserRecord,
)
from omniai.config.settings import Settings
from omniai.domain.knowledge.models import utc_now
from omniai.security.hashing import hash_api_key, hash_password, verify_password
from omniai.security.permissions import Perm, assert_permission
from omniai.security.tokens import create_session_token, generate_jti, verify_session_token


@dataclass(slots=True)
class AuthenticatedPrincipal:
    user_id: str
    email: str
    display_name: str
    tenant_id: str
    tenant_name: str
    role: str
    auth_type: str
    api_key_id: str | None = None


class RegisterInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=128)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class CreateApiKeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["tenant:read", "collections:write", "documents:write"])


class CreateTeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def ensure_bootstrap_admin(self, tenant_id: str) -> UserRecord:
        email = self._normalize_email(self._settings.bootstrap_admin_email)
        user = self._session.scalar(select(UserRecord).where(UserRecord.email == email))
        if user is None:
            user = UserRecord(
                primary_tenant_id=tenant_id,
                email=email,
                display_name=self._settings.bootstrap_admin_display_name,
                password_hash=hash_password(self._settings.bootstrap_admin_password),
                is_active=1,
            )
            self._session.add(user)
            self._session.flush()

        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.tenant_id == tenant_id,
                TenantMembershipRecord.user_id == user.id,
            )
        )
        if membership is None:
            membership = TenantMembershipRecord(
                tenant_id=tenant_id,
                user_id=user.id,
                role="OWNER",
            )
            self._session.add(membership)

        self._session.commit()
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action="bootstrap_admin.ready",
            target_type="user",
            target_id=user.id,
            detail={"email": user.email},
            commit=True,
        )
        return user

    def register(self, payload: RegisterInput, tenant_id: str) -> dict:
        if not self._settings.registration_open:
            raise PermissionError("Registration is currently disabled.")

        email = self._normalize_email(payload.email)
        existing = self._session.scalar(select(UserRecord).where(UserRecord.email == email))
        if existing is not None:
            raise ValueError("A user with that email already exists.")

        tenant = self._get_tenant(tenant_id)
        user = UserRecord(
            primary_tenant_id=tenant_id,
            email=email,
            display_name=payload.display_name.strip(),
            password_hash=hash_password(payload.password),
            is_active=1,
        )
        self._session.add(user)
        self._session.flush()

        membership = TenantMembershipRecord(
            tenant_id=tenant_id,
            user_id=user.id,
            role="MEMBER",
        )
        self._session.add(membership)
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action="auth.register",
            target_type="user",
            target_id=user.id,
            detail={"email": user.email},
            commit=False,
        )
        self._session.commit()

        principal = self._build_principal(user, tenant, membership.role, auth_type="session")
        token = self.issue_session_token(principal)
        return self._build_auth_result(principal, token)

    def login(self, payload: LoginInput) -> dict:
        from datetime import datetime, timedelta, timezone as _tz

        email = self._normalize_email(payload.email)
        user = self._session.scalar(select(UserRecord).where(UserRecord.email == email))

        # ── Lockout check ────────────────────────────────────────────────────
        # Always guard against timing-based enumeration: check lockout *before*
        # verifying the password so the response time is consistent regardless
        # of whether the user exists.
        if user is not None and user.locked_until is not None:
            now = datetime.now(_tz.utc)
            locked_ts = user.locked_until
            if locked_ts.tzinfo is None:
                locked_ts = locked_ts.replace(tzinfo=_tz.utc)
            if locked_ts > now:
                remaining = int((locked_ts - now).total_seconds() // 60) + 1
                raise PermissionError(
                    f"Account is temporarily locked. Try again in {remaining} minute(s)."
                )
            # Lock has expired — reset the counter so the account is usable again.
            user.failed_login_attempts = 0
            user.locked_until = None

        # ── Credential verification ──────────────────────────────────────────
        if user is None or not verify_password(payload.password, user.password_hash):
            # Increment failure counter for the found user (if any).
            if user is not None:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                threshold = self._settings.login_lockout_threshold
                if user.failed_login_attempts >= threshold:
                    from datetime import datetime as _dt, timedelta as _td, timezone as _tz2
                    user.locked_until = _dt.now(_tz2.utc) + _td(
                        minutes=self._settings.login_lockout_minutes
                    )
                self._session.commit()
            raise PermissionError("Invalid email or password.")

        if not bool(user.is_active):
            raise PermissionError("This user account is disabled.")

        # ── Success: reset failure counter ───────────────────────────────────
        user.failed_login_attempts = 0
        user.locked_until = None

        # ── MFA challenge ────────────────────────────────────────────────────
        if bool(user.mfa_enabled):
            # Issue a short-lived MFA challenge token instead of a full session.
            # The client presents this token to POST /v1/auth/mfa/verify.
            mfa_challenge = create_session_token(
                {
                    "sub": user.id,
                    "tenant_id": user.primary_tenant_id,
                    "role": "_mfa_challenge",  # unprivileged sentinel role
                    "exp": int(time.time()) + 300,  # 5 minutes
                    "jti": generate_jti(),
                },
                self._settings.auth_secret,
            )
            self._session.commit()
            return {
                "mfaRequired": True,
                "mfaChallengeToken": mfa_challenge,
            }

        membership = self._get_primary_membership(user.id, user.primary_tenant_id)
        tenant = self._get_tenant(membership.tenant_id)
        principal = self._build_principal(user, tenant, membership.role, auth_type="session")
        token = self.issue_session_token(principal)
        self._record_audit_event(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="auth.login",
            target_type="user",
            target_id=principal.user_id,
            detail={"auth_type": "session"},
            commit=True,
        )
        return self._build_auth_result(principal, token)

    def mfa_verify(self, challenge_token: str, code: str) -> dict:
        """Exchange an MFA challenge token for a full session token.

        Called after a successful password check when the account has MFA
        enabled.  ``challenge_token`` is the short-lived token returned by
        ``login`` with ``mfaRequired=True``.
        """
        payload = verify_session_token(challenge_token, self._settings.auth_secret)
        if payload.get("role") != "_mfa_challenge":
            raise PermissionError("Invalid MFA challenge token.")

        user = self._session.scalar(select(UserRecord).where(UserRecord.id == payload["sub"]))
        if user is None or not bool(user.is_active):
            raise PermissionError("User not available.")

        # Delegate actual TOTP / recovery-code verification to IdentityService
        from omniai.application.identity_service import IdentityService
        id_svc = IdentityService(self._session, self._settings)
        if not id_svc.verify_totp_or_recovery(user, code):
            raise PermissionError("Invalid MFA code.")

        membership = self._get_primary_membership(user.id, payload["tenant_id"])
        tenant = self._get_tenant(membership.tenant_id)
        principal = self._build_principal(user, tenant, membership.role, auth_type="session")
        token = self.issue_session_token(principal)
        self._record_audit_event(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="auth.mfa_verify",
            target_type="user",
            target_id=principal.user_id,
            detail={"auth_type": "session"},
            commit=True,
        )
        return self._build_auth_result(principal, token)

    def authenticate_session_token(self, token: str) -> AuthenticatedPrincipal:
        payload = verify_session_token(token, self._settings.auth_secret)

        # Check revocation blocklist before any DB user lookup
        jti = payload.get("jti")
        if jti:
            revoked = self._session.scalar(
                select(RevokedTokenRecord).where(RevokedTokenRecord.jti == jti)
            )
            if revoked is not None:
                raise PermissionError("Session has been revoked.")

        user = self._session.scalar(select(UserRecord).where(UserRecord.id == payload["sub"]))
        if user is None or not bool(user.is_active):
            raise PermissionError("User account is not available.")

        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user.id,
                TenantMembershipRecord.tenant_id == payload["tenant_id"],
            )
        )
        if membership is None:
            raise PermissionError("Tenant membership is not available.")

        tenant = self._get_tenant(membership.tenant_id)
        return self._build_principal(user, tenant, membership.role, auth_type="session")

    def authenticate_api_key(self, raw_key: str) -> AuthenticatedPrincipal:
        prefix = raw_key[:16]
        record = self._session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.prefix == prefix))
        if record is None or record.revoked_at is not None:
            raise PermissionError("API key is invalid or revoked.")
        if record.key_hash != hash_api_key(raw_key):
            raise PermissionError("API key is invalid or revoked.")

        user = self._session.scalar(select(UserRecord).where(UserRecord.id == record.created_by_user_id))
        if user is None or not bool(user.is_active):
            raise PermissionError("API key owner is not available.")

        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user.id,
                TenantMembershipRecord.tenant_id == record.tenant_id,
            )
        )
        if membership is None:
            raise PermissionError("API key tenant membership is not available.")

        tenant = self._get_tenant(record.tenant_id)
        record.last_used_at = utc_now()
        self._session.commit()
        return self._build_principal(
            user,
            tenant,
            membership.role,
            auth_type="api_key",
            api_key_id=record.id,
        )

    def issue_session_token(self, principal: AuthenticatedPrincipal) -> str:
        expires_at = int(time.time()) + (self._settings.session_ttl_minutes * 60)
        return create_session_token(
            {
                "sub": principal.user_id,
                "tenant_id": principal.tenant_id,
                "role": principal.role,
                "exp": expires_at,
                "jti": generate_jti(),   # unique ID enables explicit revocation
            },
            self._settings.auth_secret,
        )

    def logout(self, token: str) -> None:
        """Revoke a session token immediately.

        The token is added to the ``revoked_tokens`` blocklist so that
        subsequent requests presenting the same token are rejected even though
        the signature is still technically valid.  Expired tokens are silently
        accepted so that logging out an already-expired session never fails.
        """
        try:
            payload = verify_session_token(token, self._settings.auth_secret)
        except ValueError:
            return  # expired / malformed — nothing to revoke

        jti = payload.get("jti")
        if not jti:
            return  # legacy token without jti — can't revoke by ID

        existing = self._session.scalar(
            select(RevokedTokenRecord).where(RevokedTokenRecord.jti == jti)
        )
        if existing is not None:
            return  # already revoked

        from datetime import datetime, timezone as _tz
        self._session.add(
            RevokedTokenRecord(
                jti=jti,
                user_id=payload["sub"],
                expires_at=datetime.fromtimestamp(payload["exp"], tz=_tz.utc),
            )
        )
        self._session.commit()

    def request_password_reset(self, email: str) -> str | None:
        """Generate a one-time reset token for the user.

        Returns the raw token string (to be delivered via email/console).
        Returns ``None`` silently if the email is not found — never reveal
        whether an address exists.
        """
        user = self._session.scalar(
            select(UserRecord).where(UserRecord.email == self._normalize_email(email))
        )
        if user is None or not bool(user.is_active):
            return None

        raw_token = secrets.token_urlsafe(32)
        from omniai.security.hashing import hash_password as _hash  # reuse SHA-256 pipeline
        user.reset_token_hash = _hash(raw_token)          # store hash, never plaintext
        from datetime import datetime, timedelta, timezone as _tz
        user.reset_token_expires_at = datetime.now(_tz.utc) + timedelta(hours=1)
        self._session.commit()
        return raw_token

    def reset_password(self, token: str, new_password: str) -> None:
        """Consume a reset token and update the user's password."""
        from datetime import datetime, timezone as _tz
        from omniai.security.hashing import hash_password as _hash, verify_password as _verify

        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        now = datetime.now(_tz.utc)
        # We must find the user by hashing candidate tokens — not feasible at scale,
        # so we iterate candidates (reset tokens are short-lived and rare).
        # Scalable alternative: store a lookup-safe prefix + hash.
        users = list(self._session.scalars(
            select(UserRecord).where(
                UserRecord.reset_token_hash.is_not(None),
                UserRecord.reset_token_expires_at > now,
            )
        ))
        matched: UserRecord | None = None
        for user in users:
            if _verify(token, user.reset_token_hash or ""):
                matched = user
                break

        if matched is None:
            raise ValueError("Reset token is invalid or has expired.")

        matched.password_hash = _hash(new_password)
        matched.reset_token_hash = None
        matched.reset_token_expires_at = None
        self._session.commit()

    def list_api_keys(self, principal: AuthenticatedPrincipal) -> list[dict]:
        statement = select(ApiKeyRecord).where(ApiKeyRecord.tenant_id == principal.tenant_id)
        if principal.role not in {"OWNER", "ADMIN"}:
            statement = statement.where(ApiKeyRecord.created_by_user_id == principal.user_id)

        keys = self._session.scalars(statement.order_by(ApiKeyRecord.created_at.desc()))
        return [
            {
                "id": record.id,
                "name": record.name,
                "prefix": record.prefix,
                "scopes": self._split_scopes(record.scopes),
                "createdAt": record.created_at.isoformat(),
                "lastUsedAt": record.last_used_at.isoformat() if record.last_used_at else None,
                "revokedAt": record.revoked_at.isoformat() if record.revoked_at else None,
                "createdByUserId": record.created_by_user_id,
            }
            for record in keys
        ]

    def create_api_key(self, principal: AuthenticatedPrincipal, payload: CreateApiKeyInput) -> dict:
        assert_permission(principal.role, Perm.API_KEYS_WRITE)
        raw_key = f"omsk_{secrets.token_urlsafe(32)}"
        record = ApiKeyRecord(
            tenant_id=principal.tenant_id,
            created_by_user_id=principal.user_id,
            name=payload.name.strip(),
            prefix=raw_key[:16],
            key_hash=hash_api_key(raw_key),
            scopes=",".join(sorted(set(payload.scopes))),
        )
        self._session.add(record)
        self._session.flush()
        self._record_audit_event(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="api_key.create",
            target_type="api_key",
            target_id=record.id,
            detail={"name": record.name},
            commit=False,
        )
        self._session.commit()
        return {
            "id": record.id,
            "name": record.name,
            "prefix": record.prefix,
            "scopes": self._split_scopes(record.scopes),
            "token": raw_key,
            "createdAt": record.created_at.isoformat(),
        }

    def revoke_api_key(self, principal: AuthenticatedPrincipal, api_key_id: str) -> dict:
        record = self._session.scalar(
            select(ApiKeyRecord).where(
                ApiKeyRecord.id == api_key_id,
                ApiKeyRecord.tenant_id == principal.tenant_id,
            )
        )
        if record is None:
            raise KeyError("API key not found.")
        if principal.role not in {"OWNER", "ADMIN"} and record.created_by_user_id != principal.user_id:
            raise PermissionError("You cannot revoke this API key.")

        record.revoked_at = utc_now()
        self._record_audit_event(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="api_key.revoke",
            target_type="api_key",
            target_id=record.id,
            detail={"name": record.name},
            commit=False,
        )
        self._session.commit()
        return {"id": record.id, "revokedAt": record.revoked_at.isoformat()}

    def get_current_tenant(self, principal: AuthenticatedPrincipal) -> dict:
        tenant = self._get_tenant(principal.tenant_id)
        members = int(
            self._session.scalar(
                select(func.count(TenantMembershipRecord.id)).where(TenantMembershipRecord.tenant_id == tenant.id)
            )
            or 0
        )
        teams = int(
            self._session.scalar(select(func.count(TeamRecord.id)).where(TeamRecord.tenant_id == tenant.id)) or 0
        )
        return {
            "id": tenant.id,
            "slug": tenant.slug,
            "name": tenant.name,
            "memberCount": members,
            "teamCount": teams,
            "role": principal.role,
        }

    def list_my_memberships(self, principal: AuthenticatedPrincipal) -> list[dict]:
        statement = (
            select(TenantMembershipRecord, TenantRecord)
            .join(TenantRecord, TenantRecord.id == TenantMembershipRecord.tenant_id)
            .where(TenantMembershipRecord.user_id == principal.user_id)
            .order_by(TenantRecord.name.asc())
        )
        return [
            {
                "tenantId": membership.tenant_id,
                "tenantName": tenant.name,
                "tenantSlug": tenant.slug,
                "role": membership.role,
            }
            for membership, tenant in self._session.execute(statement)
        ]

    def list_users(self, principal: AuthenticatedPrincipal) -> list[dict]:
        assert_permission(principal.role, Perm.USERS_READ)
        statement = (
            select(TenantMembershipRecord, UserRecord)
            .join(UserRecord, UserRecord.id == TenantMembershipRecord.user_id)
            .where(TenantMembershipRecord.tenant_id == principal.tenant_id)
            .order_by(UserRecord.email.asc())
        )
        return [
            {
                "id": user.id,
                "email": user.email,
                "displayName": user.display_name,
                "role": membership.role,
                "isActive": bool(user.is_active),
                "createdAt": user.created_at.isoformat(),
            }
            for membership, user in self._session.execute(statement)
        ]

    def list_audit_events(
        self,
        principal: AuthenticatedPrincipal,
        *,
        limit: int = 50,
        before_id: str | None = None,
    ) -> dict:
        """Return a page of audit events for the principal's tenant.

        Pagination is cursor-based: pass the ``nextCursor`` value returned by
        a previous call as ``before_id`` to fetch the next page.  Results are
        always ordered newest-first (``created_at DESC, id DESC``).
        """
        assert_permission(principal.role, Perm.AUDIT_READ)
        limit = min(max(1, limit), 200)  # clamp 1–200

        statement = select(AuditEventRecord).where(
            AuditEventRecord.tenant_id == principal.tenant_id
        )

        if before_id:
            # Keyset: fetch records whose (created_at, id) tuple is strictly
            # before the anchor.  We need the anchor's created_at first.
            anchor = self._session.scalar(
                select(AuditEventRecord).where(AuditEventRecord.id == before_id)
            )
            if anchor is not None:
                from sqlalchemy import or_, and_
                statement = statement.where(
                    or_(
                        AuditEventRecord.created_at < anchor.created_at,
                        and_(
                            AuditEventRecord.created_at == anchor.created_at,
                            AuditEventRecord.id < before_id,
                        ),
                    )
                )

        statement = (
            statement
            .order_by(AuditEventRecord.created_at.desc(), AuditEventRecord.id.desc())
            .limit(limit + 1)  # fetch one extra to know if there's a next page
        )

        rows = list(self._session.scalars(statement))
        has_more = len(rows) > limit
        page = rows[:limit]

        items = [
            {
                "id": record.id,
                "action": record.action,
                "targetType": record.target_type,
                "targetId": record.target_id,
                "detail": json.loads(record.detail_json),
                "actorUserId": record.actor_user_id,
                "createdAt": record.created_at.isoformat(),
            }
            for record in page
        ]
        return {
            "items": items,
            "nextCursor": page[-1].id if has_more and page else None,
            "hasMore": has_more,
        }

    def list_teams(self, principal: AuthenticatedPrincipal) -> list[dict]:
        statement = (
            select(TeamRecord)
            .where(TeamRecord.tenant_id == principal.tenant_id)
            .order_by(TeamRecord.name.asc())
        )
        teams = list(self._session.scalars(statement))
        results: list[dict] = []
        for team in teams:
            member_count = int(
                self._session.scalar(
                    select(func.count(TeamMembershipRecord.id)).where(TeamMembershipRecord.team_id == team.id)
                )
                or 0
            )
            my_membership = self._session.scalar(
                select(TeamMembershipRecord).where(
                    TeamMembershipRecord.team_id == team.id,
                    TeamMembershipRecord.user_id == principal.user_id,
                )
            )
            results.append(
                {
                    "id": team.id,
                    "name": team.name,
                    "description": team.description,
                    "memberCount": member_count,
                    "myRole": my_membership.role if my_membership is not None else None,
                    "createdAt": team.created_at.isoformat(),
                }
            )
        return results

    def create_team(self, principal: AuthenticatedPrincipal, payload: CreateTeamInput) -> dict:
        assert_permission(principal.role, Perm.TEAM_WRITE)
        duplicate = self._session.scalar(
            select(TeamRecord).where(
                TeamRecord.tenant_id == principal.tenant_id,
                func.lower(TeamRecord.name) == payload.name.lower(),
            )
        )
        if duplicate is not None:
            raise ValueError("A team with that name already exists.")

        team = TeamRecord(
            tenant_id=principal.tenant_id,
            name=payload.name.strip(),
            description=payload.description,
        )
        self._session.add(team)
        self._session.flush()
        self._session.add(
            TeamMembershipRecord(
                team_id=team.id,
                user_id=principal.user_id,
                role="OWNER",
            )
        )
        self._record_audit_event(
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="team.create",
            target_type="team",
            target_id=team.id,
            detail={"name": team.name},
            commit=False,
        )
        self._session.commit()
        return {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "createdAt": team.created_at.isoformat(),
        }

    @staticmethod
    def principal_to_payload(principal: AuthenticatedPrincipal) -> dict:
        return {
            "userId": principal.user_id,
            "email": principal.email,
            "displayName": principal.display_name,
            "tenantId": principal.tenant_id,
            "tenantName": principal.tenant_name,
            "role": principal.role,
            "authType": principal.auth_type,
            "apiKeyId": principal.api_key_id,
        }

    def _build_auth_result(self, principal: AuthenticatedPrincipal, access_token: str) -> dict:
        return {
            "accessToken": access_token,
            "sessionTtlMinutes": self._settings.session_ttl_minutes,
            "principal": self.principal_to_payload(principal),
        }

    def _build_principal(
        self,
        user: UserRecord,
        tenant: TenantRecord,
        role: str,
        *,
        auth_type: str,
        api_key_id: str | None = None,
    ) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            role=role,
            auth_type=auth_type,
            api_key_id=api_key_id,
        )

    def _get_primary_membership(self, user_id: str, tenant_id: str) -> TenantMembershipRecord:
        membership = self._session.scalar(
            select(TenantMembershipRecord).where(
                TenantMembershipRecord.user_id == user_id,
                TenantMembershipRecord.tenant_id == tenant_id,
            )
        )
        if membership is None:
            raise PermissionError("Tenant membership is not available.")
        return membership

    def _get_tenant(self, tenant_id: str) -> TenantRecord:
        tenant = self._session.scalar(select(TenantRecord).where(TenantRecord.id == tenant_id))
        if tenant is None:
            raise KeyError("Tenant not found.")
        return tenant

    def _record_audit_event(
        self,
        *,
        tenant_id: str,
        actor_user_id: str | None,
        action: str,
        target_type: str,
        target_id: str,
        detail: dict,
        commit: bool,
    ) -> None:
        record = AuditEventRecord(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json=json.dumps(detail, separators=(",", ":"), sort_keys=True),
        )
        self._session.add(record)
        if commit:
            self._session.commit()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _split_scopes(scopes: str) -> list[str]:
        if not scopes:
            return []
        return [scope for scope in scopes.split(",") if scope]

