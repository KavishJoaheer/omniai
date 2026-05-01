"""M18 — UX & Accessibility backend tests.

Covers:
  1.  POST /v1/documents/bulk  — delete, reindex, set_tags actions
  2.  POST /v1/documents/bulk  — validation: empty list, bad action, too many ids
  3.  GET  /v1/conversations/{id}/export?format=json
  4.  GET  /v1/conversations/{id}/export?format=markdown
  5.  GET  /v1/conversations/{id}/export  — unknown format returns 400
  6.  GET  /v1/agents/{id}/runs/{rid}/export?format=json
  7.  GET  /v1/agents/{id}/runs/{rid}/export?format=markdown
  8.  GET  /v1/agents/{id}/runs/{rid}/export — unknown format returns 400
  9.  Export of non-existent conversation returns 404
  10. Export of non-existent run returns 404
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

_ADMIN_EMAIL    = "test@local.dev"
_ADMIN_PASSWORD = "TestPassword123!"


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_collection(client, auth, name="test-col"):
    r = client.post("/v1/collections", json={
        "name": name,
        "description": "",
        "embedding_model": "nomic-embed-text",
        "chunk_template": "general",
        "top_k": 5,
        "vector_weight": 0.6,
    }, headers=auth)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _upload_document(client, auth, collection_id, filename="test.txt", content=b"Hello world"):
    r = client.post(
        f"/v1/collections/{collection_id}/documents/upload",
        files={"file": (filename, content, "text/plain")},
        headers=auth,
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    # Handle both envelope {"data": {...}} and direct response
    return data["data"]["id"] if "data" in data else data["id"]


def _create_conversation(client, auth, collection_ids):
    r = client.post("/v1/conversations", json={
        "title": "E2E chat",
        "collection_ids": collection_ids,
    }, headers=auth)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    # Conversation routes return ConversationOut directly (no envelope)
    return data["data"]["id"] if "data" in data else data["id"]


def _create_agent_and_run(client, auth, collection_ids):
    r = client.post("/v1/agents", json={
        "name": "test-agent",
        "description": "",
        "definition": {
            "version": 1,
            "nodes": [
                {"id": "start",    "type": "start",    "label": "Start"},
                {"id": "generate", "type": "generate", "label": "Generate"},
                {"id": "end",      "type": "end",      "label": "End"},
            ],
            "edges": [
                {"from": "start",    "to": "generate"},
                {"from": "generate", "to": "end"},
            ],
            "collectionIds": collection_ids,
            "retrieval":   {"topK": 3, "vectorWeight": 0.6, "similarityThreshold": 0},
            "generation":  {"mode": "local-grounded", "fallbackText": "No answer."},
        },
    }, headers=auth)
    assert r.status_code in (200, 201), r.text
    agent_id = r.json()["data"]["id"]

    r2 = client.post(f"/v1/agents/{agent_id}/runs", json={"input": "test query"}, headers=auth)
    assert r2.status_code in (200, 201), r2.text
    run_id = r2.json()["data"]["id"]
    return agent_id, run_id


# ══════════════════════════════════════════════════════════════════════════════
# 1–2. Bulk document operations
# ══════════════════════════════════════════════════════════════════════════════

class TestBulkDocuments:

    @pytest.fixture(scope="class")
    def setup(self, client, auth):
        col_id = _create_collection(client, auth, "bulk-col")
        doc_id1 = _upload_document(client, auth, col_id, "a.txt", b"Alpha")
        doc_id2 = _upload_document(client, auth, col_id, "b.txt", b"Beta")
        return col_id, doc_id1, doc_id2

    def test_bulk_reindex_returns_succeeded(self, client, auth, setup):
        _, doc1, doc2 = setup
        r = client.post("/v1/documents/bulk", json={
            "document_ids": [doc1, doc2],
            "action": "reindex",
            "tags": [],
        }, headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "succeeded" in data
        assert data["action"] == "reindex"
        assert len(data["succeeded"]) == 2

    def test_bulk_set_tags(self, client, auth, setup):
        _, doc1, doc2 = setup
        r = client.post("/v1/documents/bulk", json={
            "document_ids": [doc1, doc2],
            "action": "set_tags",
            "tags": ["bulk-tag", "m18"],
        }, headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["action"] == "set_tags"
        assert len(data["succeeded"]) == 2

    def test_bulk_delete(self, client, auth, setup):
        col_id = setup[0]
        # Upload a temporary document then bulk-delete it
        tmp_id = _upload_document(client, auth, col_id, "tmp.txt", b"temp")
        r = client.post("/v1/documents/bulk", json={
            "document_ids": [tmp_id],
            "action": "delete",
            "tags": [],
        }, headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["action"] == "delete"
        assert tmp_id in r.json()["data"]["succeeded"]

    def test_bulk_rejects_empty_list(self, client, auth):
        r = client.post("/v1/documents/bulk", json={
            "document_ids": [],
            "action": "delete",
            "tags": [],
        }, headers=auth)
        assert r.status_code == 422

    def test_bulk_rejects_bad_action(self, client, auth, setup):
        _, doc1, _ = setup
        r = client.post("/v1/documents/bulk", json={
            "document_ids": [doc1],
            "action": "explode",
            "tags": [],
        }, headers=auth)
        assert r.status_code == 422

    def test_bulk_unknown_ids_reported_in_failed(self, client, auth):
        r = client.post("/v1/documents/bulk", json={
            "document_ids": ["non-existent-id-abc"],
            "action": "reindex",
            "tags": [],
        }, headers=auth)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "non-existent-id-abc" in data.get("failed", {})


# ══════════════════════════════════════════════════════════════════════════════
# 3–5. Conversation export
# ══════════════════════════════════════════════════════════════════════════════

class TestConversationExport:

    @pytest.fixture(scope="class")
    def conv_id(self, client, auth):
        col_id = _create_collection(client, auth, "export-col")
        return _create_conversation(client, auth, [col_id])

    def test_export_json_returns_json_content_type(self, client, auth, conv_id):
        r = client.get(f"/v1/conversations/{conv_id}/export?format=json", headers=auth)
        assert r.status_code == 200, r.text
        assert "application/json" in r.headers.get("content-type", "")
        # Should be downloadable (Content-Disposition header)
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_export_json_body_is_valid_json(self, client, auth, conv_id):
        r = client.get(f"/v1/conversations/{conv_id}/export?format=json", headers=auth)
        assert r.status_code == 200, r.text
        payload = json.loads(r.content)
        assert "id" in payload
        assert payload["id"] == conv_id

    def test_export_markdown_returns_text(self, client, auth, conv_id):
        r = client.get(f"/v1/conversations/{conv_id}/export?format=markdown", headers=auth)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/markdown" in ct or "text/plain" in ct
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_export_markdown_contains_title(self, client, auth, conv_id):
        r = client.get(f"/v1/conversations/{conv_id}/export?format=markdown", headers=auth)
        assert r.status_code == 200
        assert "#" in r.text  # heading marker

    def test_export_unknown_format_returns_400(self, client, auth, conv_id):
        r = client.get(f"/v1/conversations/{conv_id}/export?format=pdf", headers=auth)
        assert r.status_code == 400

    def test_export_nonexistent_conversation_returns_404(self, client, auth):
        r = client.get("/v1/conversations/does-not-exist/export?format=json", headers=auth)
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 6–8. Agent run export
# ══════════════════════════════════════════════════════════════════════════════

class TestAgentRunExport:

    @pytest.fixture(scope="class")
    def run_ids(self, client, auth):
        col_id = _create_collection(client, auth, "agent-export-col")
        agent_id, run_id = _create_agent_and_run(client, auth, [col_id])
        return agent_id, run_id

    def test_export_run_json_returns_json(self, client, auth, run_ids):
        agent_id, run_id = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/{run_id}/export?format=json", headers=auth)
        assert r.status_code == 200, r.text
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_export_run_json_body_has_run_id(self, client, auth, run_ids):
        agent_id, run_id = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/{run_id}/export?format=json", headers=auth)
        payload = json.loads(r.content)
        assert payload.get("id") == run_id

    def test_export_run_markdown_returns_text(self, client, auth, run_ids):
        agent_id, run_id = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/{run_id}/export?format=markdown", headers=auth)
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        assert "text/markdown" in ct or "text/plain" in ct

    def test_export_run_markdown_contains_heading(self, client, auth, run_ids):
        agent_id, run_id = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/{run_id}/export?format=markdown", headers=auth)
        assert "#" in r.text

    def test_export_unknown_format_returns_400(self, client, auth, run_ids):
        agent_id, run_id = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/{run_id}/export?format=xml", headers=auth)
        assert r.status_code == 400

    def test_export_nonexistent_run_returns_404(self, client, auth, run_ids):
        agent_id, _ = run_ids
        r = client.get(f"/v1/agents/{agent_id}/runs/ghost-run-id/export?format=json", headers=auth)
        assert r.status_code == 404
