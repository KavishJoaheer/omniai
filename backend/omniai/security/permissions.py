from __future__ import annotations

ROLE_NAMES: frozenset[str] = frozenset({"OWNER", "ADMIN", "MEMBER", "VIEWER"})


class Perm:
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    USERS_READ = "users:read"
    AUDIT_READ = "audit:read"
    TEAM_READ = "team:read"
    TEAM_WRITE = "team:write"
    COLLECTIONS_READ = "collections:read"
    COLLECTIONS_WRITE = "collections:write"
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    PROVIDERS_READ = "providers:read"
    PROVIDERS_WRITE = "providers:write"
    API_KEYS_READ = "api_keys:read"
    API_KEYS_WRITE = "api_keys:write"


_VIEWER: frozenset[str] = frozenset(
    {
        Perm.TENANT_READ,
        Perm.TEAM_READ,
        Perm.COLLECTIONS_READ,
        Perm.DOCUMENTS_READ,
        Perm.PROVIDERS_READ,
    }
)
_MEMBER: frozenset[str] = _VIEWER | frozenset(
    {
        Perm.COLLECTIONS_WRITE,
        Perm.DOCUMENTS_WRITE,
        Perm.TEAM_WRITE,
        Perm.API_KEYS_READ,
        Perm.API_KEYS_WRITE,
    }
)
_ADMIN: frozenset[str] = _MEMBER | frozenset(
    {
        Perm.USERS_READ,
        Perm.AUDIT_READ,
        Perm.PROVIDERS_WRITE,
    }
)
_OWNER: frozenset[str] = _ADMIN | frozenset({Perm.TENANT_WRITE})


_ROLE_TO_PERMS: dict[str, frozenset[str]] = {
    "VIEWER": _VIEWER,
    "MEMBER": _MEMBER,
    "ADMIN": _ADMIN,
    "OWNER": _OWNER,
}


def permissions_for(role: str) -> frozenset[str]:
    if role not in _ROLE_TO_PERMS:
        raise PermissionError(f"Unknown role: {role}")
    return _ROLE_TO_PERMS[role]


def role_has(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def assert_permission(role: str, permission: str) -> None:
    if not role_has(role, permission):
        raise PermissionError(f"Role {role} lacks permission {permission}.")
