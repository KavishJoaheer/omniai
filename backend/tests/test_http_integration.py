"""HTTP integration tests.

Uses FastAPI's ``TestClient`` (httpx-backed) to exercise full request/response
cycles including auth middleware, route handlers, and the database layer.
These are intentionally *not* unit tests — they run against the real
application stack (SQLite + InMemorySearchEngine).

Credentials are taken from the conftest bootstrap values so the same
test DB is reused without extra setup.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# These match conftest.py _set_test_env
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
    """Return a valid session token for the bootstrap admin."""
    response = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ── Health ─────────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["status"] == "healthy"
    assert "environment" in body


# ── Auth: login / logout / me ──────────────────────────────────────────────

def test_login_valid(client):
    r = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert "accessToken" in data
    assert data["principal"]["role"] == "OWNER"


def test_login_wrong_password(client):
    r = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": "definitelyWrong99!"},
    )
    assert r.status_code == 401


def test_me_authenticated(client, auth_headers):
    r = client.get("/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["email"] == _ADMIN_EMAIL


def test_me_unauthenticated(client):
    # Use explicit empty Authorization to bypass the shared cookie jar
    r = client.get("/v1/auth/me", headers={"Authorization": ""}, cookies={"omniai_session": ""})
    assert r.status_code == 401


def test_logout_revokes_token(client):
    """After logout the same token must be rejected."""
    login_r = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    token = login_r.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}

    # Token works before logout
    assert client.get("/v1/auth/me", headers=headers).status_code == 200

    # Logout
    logout_r = client.post("/v1/auth/logout", headers=headers)
    assert logout_r.status_code == 200

    # Token must now be rejected
    assert client.get("/v1/auth/me", headers=headers).status_code == 401


# ── Password reset ──────────────────────────────────────────────────────────

def test_password_reset_flow(client):
    """Full round-trip: request reset → consume token → login with new password."""
    r = client.post(
        "/v1/auth/request-password-reset",
        json={"email": _ADMIN_EMAIL},
    )
    assert r.status_code == 202
    reset_token = r.json()["data"]["reset_token"]
    assert reset_token is not None

    new_pw = "NewIntPass456!"
    r2 = client.post(
        "/v1/auth/reset-password",
        json={"token": reset_token, "new_password": new_pw},
    )
    assert r2.status_code == 200

    # Login with new password
    r3 = client.post(
        "/v1/auth/login",
        json={"email": _ADMIN_EMAIL, "password": new_pw},
    )
    assert r3.status_code == 200

    # Restore original password
    r4 = client.post(
        "/v1/auth/request-password-reset",
        json={"email": _ADMIN_EMAIL},
    )
    token2 = r4.json()["data"]["reset_token"]
    client.post(
        "/v1/auth/reset-password",
        json={"token": token2, "new_password": _ADMIN_PASSWORD},
    )


def test_reset_token_single_use(client):
    """A reset token must not be usable twice."""
    r = client.post(
        "/v1/auth/request-password-reset",
        json={"email": _ADMIN_EMAIL},
    )
    token = r.json()["data"]["reset_token"]

    client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "TempPw12345!"},
    )

    r2 = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherPw123!"},
    )
    assert r2.status_code == 400

    # Restore
    r3 = client.post(
        "/v1/auth/request-password-reset",
        json={"email": _ADMIN_EMAIL},
    )
    t2 = r3.json()["data"]["reset_token"]
    client.post(
        "/v1/auth/reset-password",
        json={"token": t2, "new_password": _ADMIN_PASSWORD},
    )


# ── Collections CRUD ──────────────────────────────────────────────────────

def test_create_and_list_collection(client, auth_headers):
    r = client.post(
        "/v1/collections",
        json={
            "name": "HTTP Integration Test Col",
            "description": "Created by integration test",
            "embedding_model": "nomic-embed-text",
            "chunk_template": "general",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    col = r.json()["data"]
    col_id = col["id"]
    assert col["name"] == "HTTP Integration Test Col"

    list_r = client.get("/v1/collections", headers=auth_headers)
    assert list_r.status_code == 200
    ids = [c["id"] for c in list_r.json()["data"]]
    assert col_id in ids

    client.delete(f"/v1/collections/{col_id}", headers=auth_headers)


def test_collection_requires_auth(client):
    r = client.get("/v1/collections", headers={"Authorization": ""}, cookies={"omniai_session": ""})
    assert r.status_code == 401


# ── Document upload ────────────────────────────────────────────────────────

def test_upload_document(client, auth_headers):
    col_r = client.post(
        "/v1/collections",
        json={"name": "Upload HTTP Test", "embedding_model": "nomic-embed-text", "chunk_template": "general"},
        headers=auth_headers,
    )
    col_id = col_r.json()["data"]["id"]

    r = client.post(
        f"/v1/collections/{col_id}/documents/upload",
        files={"file": ("hello.txt", b"Hello world! This is a test document.", "text/plain")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    doc = r.json()["data"]
    assert doc["name"] == "hello.txt"
    assert doc["collection_id"] == col_id

    client.delete(f"/v1/documents/{doc['id']}", headers=auth_headers)
    client.delete(f"/v1/collections/{col_id}", headers=auth_headers)


# ── Sandbox ───────────────────────────────────────────────────────────────

def test_sandbox_run_python(client, auth_headers):
    r = client.post(
        "/v1/sandbox/run",
        json={"code": "print(2 + 2)", "timeout_seconds": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["exit_code"] == 0
    assert "4" in result["stdout"]


def test_sandbox_captures_stderr(client, auth_headers):
    r = client.post(
        "/v1/sandbox/run",
        json={"code": "import sys; sys.stderr.write('oops\\n')", "timeout_seconds": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert "oops" in r.json()["data"]["stderr"]


# ── Agents ────────────────────────────────────────────────────────────────

def test_create_and_run_agent(client, auth_headers):
    r = client.post(
        "/v1/agents",
        json={"name": "HTTP Integration Agent", "description": "Test"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    agent_id = r.json()["data"]["id"]

    run_r = client.post(
        f"/v1/agents/{agent_id}/runs",
        json={"input": "Hello"},
        headers=auth_headers,
    )
    assert run_r.status_code == 201
    run = run_r.json()["data"]
    # May FAIL if Ollama not available — both outcomes are valid
    assert run["status"] in {"COMPLETED", "FAILED"}

    client.delete(f"/v1/agents/{agent_id}", headers=auth_headers)


# ── Rate limiter sanity ────────────────────────────────────────────────────

def test_rate_limiter_does_not_crash_on_valid_requests(client, auth_headers):
    for _ in range(5):
        r = client.get("/v1/auth/me", headers=auth_headers)
        assert r.status_code in {200, 429}
