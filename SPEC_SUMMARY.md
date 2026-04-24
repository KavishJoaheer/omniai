# Phase 1 — Spec Review: Omni-AI

Clean-room summary of `SPEC.md`. Built from the spec only; no external RAG
product source or docs consulted.

## Project Parameters (locked)
- **PRODUCT_NAME:** Omni-AI
- **PRODUCT_SHORT:** `omniai`
- **ORG_NAME:** Mauritius Telecom
- **TARGET_LICENSE:** *None declared yet* — treating repo as proprietary /
  all-rights-reserved until you pick one. No LICENSE file written until then.
  SPDX headers will use `SPDX-License-Identifier: LicenseRef-Proprietary`
  as a placeholder, trivially replaceable later.
- **BACKEND_STACK (proposed):** Python 3.12, FastAPI (HTTP + SSE), Uvicorn,
  Pydantic v2, SQLAlchemy 2 + Alembic, Celery or Arq for workers, httpx for
  provider clients.
- **FRONTEND_STACK (proposed):** TypeScript + React 18 + Vite, TanStack
  Query, Zustand for local state, Tailwind + Radix primitives, React Flow
  for the Agent Builder canvas, i18next (incl. RTL), Vitest + Playwright.
- **DATABASE_CHOICES (proposed):**
  - Relational: **PostgreSQL** primary (MySQL/OceanBase behind same
    interface per §10.5).
  - Search/vector: **OpenSearch** default (Elasticsearch, embedded Infinity
    as alternates per §10.4).
  - Object store: **MinIO** default (S3/Azure/OSS/GCS via the same
    interface per §10.6).
  - Cache/queue: **Redis** (Valkey-compatible per §10.7).
  - Sandbox: **gVisor**-wrapped container runner for Code Executor nodes.
- **DEPLOYMENT_TARGET:** Docker Compose (single-node dev/prod) **and**
  Kubernetes Helm chart (cluster).

---

## Section-by-Section Understanding

### §1 Overview
Self-hostable, multi-tenant, model-agnostic knowledge platform. Two
headline capabilities: (a) grounded QA with citations over ingested
documents, (b) visual agent/workflow builder. Target users span knowledge
workers, developers, admins, workflow builders.

### §2 Feature Inventory
74 features across three tiers: Core (F1–F19) = MVP; Standard (F20–F52) =
mainstream capability; Extended (F53–F74) = pluggability, MCP, deployment,
research modes. Inventory is authoritative and referenced elsewhere.

### §3 Personas
Six personas (Ada knowledge worker, Bao developer, Chidi admin, Dana
workflow builder, Eun widget end-user, Farah data steward) give concrete
end-to-end journeys that map onto the acceptance tests in §15.

### §4 Functional Spec
Detailed behavior for 33 subsections covering: Knowledge Collections,
Documents, Multi-format ingestion (PDF/DOC/PPT/XLS/CSV/TXT/MD/HTML/EML/
images/video), 10 chunking templates, 6-stage parse pipeline (Fetch →
Extract → Chunk → Enrich → Embed → Index), chunk review/edit, embedding
model binding, retrieval testing, Chat Assistant (hybrid retrieval + rerank
+ citations + streaming + fallback), provider management, tenants/teams/
roles (OWNER/ADMIN/MEMBER/VIEWER), API + keys, Agent Builder with 15+ node
types, agent memory (KV + semantic), sessions/publishing/sharing, voice
in/TTS out, AI Search, cross-language retrieval, parent-child chunking, KG
index, summary tree, auto-tagging, metadata-filtered retrieval, TOC,
keyword weighting, structured output, sandbox code, charts, external
connectors, MCP (server + client), admin/CLI, embed widget, multi-lang UI
inc. RTL, deep-research mode.

### §5 External API
`/v1/*` REST under a Bearer-API-key scheme with envelope
`{code,message,data}`. Resources: collections, documents, chunks, metadata,
retrieve, assistants + sessions (SSE messages), OpenAI-compatible endpoints
at `/v1/assistants/{id}/openai/chat/completions` and the agent equivalent,
agents (runs/cancel/webhooks/publish/export/import), memory, providers,
users/teams/tenants/api-keys, MCP. Standard HTTP status codes, rate limits
(60 rpm / 10 concurrent streams / 1 upload in flight per collection),
idempotency via `Idempotency-Key` header within 24h.

### §6 Data Model (Logical)
20 entities: Tenant, User, Team, ApiKey, Provider, Collection, Document,
Chunk, EmbeddingRecord (logical), GraphNode/Edge, SummaryTreeNode,
Assistant, Session, Message, Agent, AgentRun, Memory, Connector, Pipeline,
AuditEvent. Document status machine: PENDING → PARSING → EMBEDDING →
INDEXING → READY / FAILED / CANCELLED.

### §7 Ingestion Pipelines
Six-stage black-box with at-least-once + idempotent writes keyed on doc
version. Re-ingestion triggered by embedding change, template change, chunk
edit, doc update. Visibility target: <10s from INDEXING→READY until
searchable.

### §8 Retrieval & Generation
Query flow: rewrite → dense ∥ sparse → fusion → optional rerank → KG/TOC
expansion → context packing → LLM → citation mapping → final usage event.
SSE events: `message.delta`, `tool.call`, `reference`, `error`, `usage`,
`done`. OpenAI-compat variant with opt-in references via `extra_body`.

### §9 Agents
JSON graph of typed nodes with typed ports. Control-flow primitives
(sequence, branch, loop, parallel, early exit), state (variables,
aggregators, memory), I/O (Start/Message/End/User Feedback), compute
(Generate/Retrieval/Code/Keyword/Chart/ExternalSearch/ToolInvocation).
Execution modes sync / streaming SSE / async-poll / webhook-triggered.
Retry/backoff per node. Publishing freezes a version and exposes public
chat URL + iframe + OpenAI-compat endpoint + webhooks.

### §10 Integration Matrix
Lists supported (not mandated) LLM providers (~40), embedding/reranker
providers, vector/search engines (3), relational stores (3), object stores
(5), caches (2), document connectors (~22), auth (local + OIDC/SAML +
API keys), voice ASR/TTS, MCP bidirectional.

### §11 Configuration Surface
Four layers: deployment env vars, service file config, per-tenant, per-
user. Table of env vars including `HTTP_PORT=9380`, pluggable kinds
(DB/SEARCH/OBJECT_STORE/CACHE), `JWT_SECRET`, `ENCRYPTION_KEY`,
`SANDBOX_KIND`, quotas, telemetry opt-in.

### §12 Non-Functional
Perf: retrieval p50 ≤150ms / p95 ≤500ms at topK=10 over ≤1M chunks;
first-token p50 ≤1.5s. Throughput ≥60 turns/min/node, ≥100 concurrent
streams/cluster. Min hw 4C/16G/50G. Obs: structured JSON logs with
correlation ids, Prom metrics at `/metrics`, OTel traces. Security:
per-tenant partition key, encrypted secrets at rest, RBAC, sandbox for
user code, audit trail for privileged actions.

### §13 Deployment
Roles: API, Worker, DB, Search, Object store, Cache, Sandbox runner.
Modes: single-node Compose, clustered (scaled API+workers), Kubernetes
Helm. Async worker queue lives on cache.

### §14 UI/UX
18 screens (S1–S18). Dark/light, RTL, WCAG 2.1 AA, ⌘K global search,
toasts, progress bars, confirmation modals. Chat screen carries
citation-chip drawer, voice in, TTS per message, thinking-mode toggle,
model-comparison up to 3 side-by-side. Agent Builder is a React-Flow-
class canvas with node palette, per-node inspector, variable panel, test
run, version history.

### §15 Acceptance Tests
20 end-to-end scenarios (AT-01 happy path chat through AT-20 backup/
restore). These become the project's acceptance gate — every one must
pass as an automated test for "done."

### §16 Non-Goals
No training/fine-tuning, not a general vector DB, not a BPM engine, no
billing, no native mobile, no real-time collab editing, no air-gapped PKI,
no model router/cost optimizer, no BI dashboards, no document editing.

### §17 Open Questions
15 explicit open questions the spec leaves for us (chunk-edit versioning,
retention, fusion formula, reranker auto-recommend, cross-collection topK
split, embed model migration UX, memory conflicts, webhook security,
sandbox stdlib, publish review, connector incrementality, rate-limit UX,
OpenAI-compat scope, citation stability across re-parse, answer language).

---

## Ambiguities / Contradictions / Underspecified Areas
Grouped. I'd like your decision before finalizing `ARCHITECTURE.md`.

**A. Scope & schedule**
1. **Extended tier timing.** §2 lists Extended features (F53–F74: MCP, plug-
   gable engines, K8s, ARM64, Deep Research, etc.). Should all ship with
   M1–M10, or is Extended "best-effort after M10"?
2. **Connector breadth.** §10.8 lists ~22 connectors. I propose M9
   implements *one* reference connector (local folder watcher) plus the
   plugin interface; the other 21 become future add-ons. Confirm.
3. **LLM/embed/rerank provider breadth.** §10.1 lists ~40 LLM vendors.
   Propose shipping the plugin interface + 3 reference adapters (OpenAI-
   compat, Ollama, Anthropic). Rest = future plugins.
4. **Voice ASR/TTS in M-series.** §10.10 names specific vendors — not free.
   Ship an ASR/TTS *interface* plus a local `faster-whisper`/Piper adapter
   for dev, or defer entirely until provider keys are available?

**B. Security/compliance defaults (open questions 1, 2, 8, 10)**
5. **Chunk edit versioning** — destructive or versioned? Compliance-safe
   default = versioned + soft-delete; costs some storage. Your call.
6. **Agent-run retention TTL.** Default 90 days with per-tenant override?
7. **Webhook security.** Default = HMAC-signed header + 5-minute replay
   window + per-hook secret. OK?
8. **Publishing review workflow.** Spec leaves open. Default = no review;
   published = immediately public within the tenant; org-admin can
   revoke. OK?

**C. Retrieval semantics (open questions 3, 5, 14, 15)**
9. **Fusion formula.** Default to linear weighted combination of
   normalized dense + sparse scores (user-settable weight, §5.7
   `vectorWeight`). Learned fusion deferred.
10. **Cross-collection topK split.** Default = by fused score globally
    (not round-robin). OK?
11. **Citation stability across re-parse.** Default = old chunk ids are
    preserved as tombstones; prior answers still render text but are
    marked "source re-parsed." Alt: hard-break with a banner.
12. **Cross-language answer language.** Default = reply in the language
    of the user's *original* query, not the translated fan-out.

**D. API surface choices (open question 13)**
13. **OpenAI-compat scope.** §5.9 specifies `/chat/completions` + tool
    calls. Propose also implementing `/v1/models` (listing available
    assistant/agent ids as "models") and `/v1/embeddings` (proxy to
    registered embedding provider). Defer `/v1/images`. OK?

**E. Sandbox (open question 9)**
14. **Sandbox stdlib.** Python: stdlib minus {`os`, `subprocess`,
    `ctypes`, `socket` (unless network allowed), filesystem writes}.
    Third-party: whitelist `requests`, `httpx`, `pandas`, `numpy`,
    `pydantic`. JS: Node runtime with a curated `package.json`. OK?

**F. Data model details**
15. **`EmbeddingRecord` storage.** Spec calls it "logical." I'd store
    vectors directly in the search engine (OpenSearch dense_vector)
    rather than a separate table; the logical record lives as an index
    document. Confirm.
16. **Parent-child chunking (§4.20).** Is the "parent" a larger chunk, a
    section block from extraction, or both? I'll implement: every chunk
    may have `parentChunkId` pointing to an auxiliary "context chunk" the
    extractor produced; small chunks embed for recall, parent text packs
    for LLM context.
17. **Pipeline stages as DAG or linear?** §4.5 lists 6 ordered stages.
    §9 agent DAG is distinct. I'll make ingestion pipelines linear
    (list of stages) for M1–M8, upgrade to DAG only if a feature
    requires it.

**G. UX scope**
18. **Model-comparison mode (§14 S8)** up to 3 answers side-by-side.
    Confirm MVP includes it (M4) or defer to M6?
19. **Knowledge Graph UI browser (§14 S4 KG tab, §4.21, AT-12).**
    Implementation cost is significant. Confirm M-series placement —
    I'd put it in M7 or later, not M3.

**H. Deployment**
20. **ARM64 support (F61).** Multi-arch Docker images from day one, or
    x86_64-only until a user requests ARM?
21. **GPU requirement.** `GPU_ENABLED=false` by default; deep-layout
    parser and local embedding models skipped when unset. OK?

**I. Naming sanity check**
The spec's domain vocabulary uses **Knowledge Collection**, **Document**,
**Chunk**, **Assistant**, **Agent**, **Session**, **Run**, **Pipeline**,
**Provider**, **Connector**, **Memory**, **Tenant/Team**, **Node/Edge/
Port** — I'll use these throughout. Product surface = **Omni-AI**. Python
package root = **`omniai`**. HTTP prefix stays `/v1` per §5. OK?

---

## Flags — Nothing Product-Specific Spotted
Per clean-room rules: the spec reads as vendor-neutral behavior. The only
places it names specific vendors are the integration matrix in §10 and
voice providers in §10.10, which are clearly marked "supported options,
not mandated." No architectural blueprints or internal naming from any
specific RAG product appear in `SPEC.md`. No action needed.

---

## Next Step
Awaiting your answers to items **1–21** above (or a "you decide with the
proposed defaults" blanket). Then I produce `ARCHITECTURE.md` per Phase 1
step 2, wait for approval, then `MILESTONES.md`, then code.
