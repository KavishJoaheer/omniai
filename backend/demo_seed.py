"""
Demo seeder -- run ONCE after the backend is up to pre-load sample data.

Usage:
    python demo_seed.py

What it does:
  1. Logs in as the bootstrap admin
  2. Creates a "Company Knowledge Base" collection (idempotent)
  3. Uploads a sample FAQ document (plain text, no external dependencies)
  4. Waits for it to reach READY status (requires Ollama for embedding)
  5. Creates a public Deploy Manager deployment (idempotent)
  6. Prints demo URLs and credentials

Requirements: backend must be running on http://localhost:9380
"""
from __future__ import annotations

import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

BASE = "http://localhost:9380"
EMAIL = "admin@omniai.local"
PASSWORD = "Admin12345!"

SAMPLE_TEXT = """\
Omni-AI Platform -- Frequently Asked Questions

Q: What is Omni-AI?
A: Omni-AI is a self-hosted, local-first Retrieval-Augmented Generation (RAG) platform.
   It lets your team upload documents and ask questions that are answered using the actual
   content in those documents -- not guessed by a language model.

Q: How does RAG work?
A: When you ask a question, Omni-AI:
   1. Converts your question into an embedding (a vector of numbers representing meaning).
   2. Searches indexed document chunks for the most semantically similar passages.
   3. Feeds those passages as context to the language model.
   4. Returns the LLM answer along with citations pointing back to the exact source chunks.

Q: What document types are supported?
A: PDF (with optional OCR fallback for scanned pages), plain text, Markdown, DOCX, and HTML.
   Support for PPTX and XLSX is on the roadmap.

Q: What chunking strategies are available?
A: Four built-in templates:
   - general: fixed-size overlapping windows (512 tokens, 64-token overlap)
   - qa: extracts Q&A pairs from structured documents
   - small-to-big: 100-word child chunks nested inside 400-word parent chunks;
     retrieval expands child hits to the full parent for richer LLM context
   - sentence-window: retrieves at sentence level, expands to surrounding sentences

Q: Does Omni-AI support on-premise deployment?
A: Yes. The entire stack runs locally with Docker Compose or Kubernetes (Helm chart included).
   No data ever leaves your infrastructure unless you choose a cloud LLM provider.

Q: What LLM providers are supported?
A: Ollama (local, default), OpenAI, Anthropic Claude, and Google Gemini.
   Providers are configured in the Admin -> Providers panel without restarting.

Q: What is the Deploy Manager?
A: Deploy Manager lets you publish a collection or agent as a public chat URL.
   Each deployment gets a unique /c/<slug> endpoint with configurable daily quotas
   and branding settings -- no login required for end users.

Q: What is the Sandbox?
A: The Sandbox is a confined Python execution environment for agent code nodes.
   Each run gets a fresh temp directory with a scrubbed environment (no secrets leak),
   an asyncio-enforced timeout, and artifact collection for files the code writes.

Q: How is data secured?
A: Provider API keys and secrets are encrypted at rest using Fernet symmetric
   encryption (ENCRYPTION_KEY setting). Sessions use signed JWT tokens.
   Per-collection RBAC controls which team members can see or edit each collection.
"""


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _call(method: str, path: str, data=None, token: str | None = None,
          content_type: str = "application/json") -> tuple[int, dict]:
    """Return (status_code, parsed_json). Never raises on HTTP errors."""
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": content_type}
    if token:
        headers["Cookie"] = f"omniai_session={token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode(errors="replace")
            payload = json.loads(body_text)
        except Exception:
            payload = {"detail": body_text[:200] if 'body_text' in dir() else str(exc)}
        return exc.code, payload


def api(method: str, path: str, data=None, token: str | None = None) -> dict:
    """Call and raise if not 2xx."""
    code, payload = _call(method, path, data=data, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"HTTP {code} {method} {path}: {payload.get('detail', payload)}")
    return payload


def ollama_running() -> bool:
    """Quick check: is Ollama listening on :11434?"""
    try:
        with urllib.request.urlopen("http://localhost:11434/", timeout=3) as _:
            return True
    except Exception:
        return False


def upload_file(col_id: str, filename: str, content: bytes, token: str) -> dict:
    """POST multipart/form-data file upload.

    With WORKER_INLINE=true the server runs parse+embed+index inside this
    request, so timeout must be generous (Ollama embedding can take 30-60s).
    """
    boundary = "OmniDemoBoundaryXx7MA4YWxk"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: text/plain\r\n\r\n",
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body_bytes = b"".join(parts)
    url = f"{BASE}/v1/collections/{col_id}/documents/upload"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Cookie": f"omniai_session={token}",
    }
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:   # 120s: inline pipeline
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"Upload failed {exc.code}: {body_text[:200]}") from exc


def wait_ready(token: str, doc_id: str, timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = api("GET", f"/v1/documents/{doc_id}/status", token=token)
            status = resp.get("data", {}).get("status", "UNKNOWN")
            print(f"    status: {status}")
            if status == "READY":
                return True
            if status == "FAILED":
                return False
        except Exception as exc:
            print(f"    poll error: {exc}")
        time.sleep(2)
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Health check
    print("Checking backend health ...")
    code, payload = _call("GET", "/v1/health")
    if code != 200:
        print(f"\n  ERROR: backend not reachable at {BASE} (got {code})")
        print("  Start it first:")
        print("    cd backend")
        print("    uvicorn main:app --host 0.0.0.0 --port 9380\n")
        sys.exit(1)
    print(f"  OK: {payload.get('data', {}).get('status', 'unknown')}")

    # 2. Login
    print(f"\nLogging in as {EMAIL} ...")
    login = api("POST", "/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = login["data"]["accessToken"]
    print("  login OK")

    # 3. Create or reuse collection
    print("\nEnsuring 'Company Knowledge Base' collection ...")
    code, col_resp = _call("POST", "/v1/collections", token=token, data={
        "name": "Company Knowledge Base",
        "description": "Sample FAQ collection for the demo",
        "embedding_model": "nomic-embed-text",
        "chunk_template": "small-to-big",
        "system_prompt": (
            "You are a helpful assistant. Answer using only the provided context. "
            "Always cite your sources with [N] markers."
        ),
        "top_k": 8,
        "vector_weight": 0.6,
    })
    if 200 <= code < 300:
        col_id = col_resp["data"]["id"]
        print(f"  created: {col_id}")
    elif code == 409:
        # Already exists -- find it
        all_cols = api("GET", "/v1/collections", token=token)
        existing = [c for c in all_cols["data"] if c["name"] == "Company Knowledge Base"]
        if not existing:
            print("  409 conflict but collection not found -- aborting")
            sys.exit(1)
        col_id = existing[0]["id"]
        print(f"  already exists: {col_id}")
    else:
        print(f"  ERROR {code}: {col_resp}")
        sys.exit(1)

    # 4. Upload sample document (only if Ollama is available)
    print("\nChecking Ollama ...")
    has_ollama = ollama_running()
    if has_ollama:
        print("  Ollama is running - uploading sample FAQ document ...")
        print("  (inline pipeline: parse -> embed -> index, takes 20-60s) ...")
        doc_id = None
        try:
            doc_resp = upload_file(
                col_id=col_id,
                filename="omni-ai-faq.txt",
                content=SAMPLE_TEXT.encode("utf-8"),
                token=token,
            )
            doc_id = doc_resp["data"]["id"]
            status = doc_resp.get("data", {}).get("status", "UNKNOWN")
            print(f"  done: {doc_id}  status={status}")
        except RuntimeError as exc:
            if "duplicate" in str(exc).lower() or "already" in str(exc).lower():
                print("  (document already exists, skipping)")
            else:
                print(f"  upload error: {exc}")
                print("  (upload manually from the Knowledge page after seeding)")
    else:
        print("  Ollama not detected on :11434")
        print("  Skipping document upload (inline pipeline needs Ollama to embed)")
        print("  To enable chat, run:")
        print("    ollama pull llama3.2")
        print("    ollama pull nomic-embed-text")
        print("  Then re-run this script OR upload via the Knowledge page.")

    # 6. Create public deployment (idempotent)
    print("\nEnsuring public deployment 'demo-chat' ...")
    code, dep_resp = _call("POST", "/v1/deployments", token=token, data={
        "name": "Demo Public Chat",
        "slug": "demo-chat",
        "kind": "public_chat",
        "target_kind": "collection",
        "target_id": col_id,
        "anonymous_allowed": True,
        "daily_message_quota": 200,
        "branding": {"title": "Omni-AI Demo", "accent": "#6366f1"},
    })
    if 200 <= code < 300:
        dep_id = dep_resp["data"]["id"]
        dep_slug = dep_resp["data"]["slug"]
        print(f"  created: {dep_id}  slug={dep_slug}")
    elif code in (409, 422):
        print("  deployment already exists, reusing")
        dep_slug = "demo-chat"
    else:
        print(f"  WARNING {code}: {dep_resp.get('detail', dep_resp)}")
        dep_slug = "demo-chat"

    # 7. Print instructions
    sep = "=" * 62
    print(f"\n{sep}")
    print("  DEMO READY")
    print(sep)
    print(f"\n  Frontend:     http://localhost:5173")
    print(f"  API docs:     http://localhost:9380/docs")
    print(f"  Metrics:      http://localhost:9380/v1/metrics")
    print(f"  Public chat:  http://localhost:9380/c/{dep_slug}/info\n")
    print(f"  Login:")
    print(f"    Email:    {EMAIL}")
    print(f"    Password: {PASSWORD}\n")
    print("  Demo flow (5 min):")
    print("    1. Overview  - live stats: collections, docs, agents, convos")
    print("    2. Knowledge - upload a PDF, watch PENDING->READY, inspect chunks")
    print("    3. Chat      - ask a question, see streamed answer + citations")
    print("    4. Search    - raw retrieval, toggle reranking on/off")
    print("    5. Agents    - show agent builder (code node uses Sandbox)")
    print("    6. Browser tab: GET /c/demo-chat/info (Deploy Manager)")
    print("    7. API docs tab: swagger at /docs (industry-grade REST API)")
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
