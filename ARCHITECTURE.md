# ARCHITECTURE.md — Omni-AI

Clean-room architecture for the Omni-AI knowledge platform, derived
solely from `SPEC.md` and the decisions recorded in `SPEC_SUMMARY.md`
(all 21 items locked to proposed defaults).

Owner: Mauritius Telecom · Codename: Omni-AI · Package root: `omniai`
HTTP prefix: `/v1` · Default port: `9380` · License: proprietary
placeholder (`SPDX-License-Identifier: LicenseRef-Proprietary`).

---

## 1. Design Principles

1. **Spec-traceable.** Every module maps to a Section/Feature id in
   `SPEC.md`. Tests cite the AT-xx acceptance scenarios from §15.
2. **Hexagonal / ports-and-adapters.** A pure domain core depends on no
   infrastructure. Adapters implement ports for DB, search, object
   store, cache, LLM, embedding, reranker, ASR, TTS, connectors,
   sandbox, MCP. New adapters never touch domain code.
3. **Registry-driven.** Every pluggable capability (chunk template,
   parser, connector, provider kind, node type, pipeline stage) is
   discovered via a registry populated at startup. Control flow never
   branches on vendor strings.
4. **Feature-deletable.** Each non-core feature lives in a single
   directory behind a config flag. Removing the directory plus flipping
   the flag must leave the rest of the system compiling and passing.
5. **Tenant-partitioned by construction.** A `TenantContext` object is
   required to construct any repository or service method — cross-
   tenant calls are not expressible.
6. **Observable at every boundary.** Structured JSON logs with a
   `correlation_id`, Prometheus metrics per port, OpenTelemetry spans
   across async hand-offs.
7. **At-least-once + idempotent.** Async work is keyed by a stable
   `(document_id, version)` or `(run_id, node_id, attempt)` so replays
   are safe.
8. **Explicit schemas.** Pydantic v2 at every API surface; typed
   TypeScript zod schemas at the frontend; no `any` / `dict[str, Any]`
   across module boundaries.

---

## 2. Service Decomposition

Processes that run independently in production. In dev-mode Compose they
may be collapsed (the `worker` can run in-process in a dev flag), but
the boundaries are preserved in code.

| Service | Process name | Responsibility | State |
|---|---|---|---|
| **API** | `omniai-api` | FastAPI app serving `/v1/*`, SSE streams, OpenAI-compat, MCP server endpoints, static UI assets | Stateless |
| **Worker** | `omniai-worker` | Consumes queues: parsing, embedding, indexing, KG build, summary-tree build, connector sync, agent-run driver | Stateless |
| **Scheduler** | `omniai-scheduler` | Fires periodic triggers: connector cron, retention GC, metrics rollup | Singleton (leased in cache) |
| **Sandbox runner** | `omniai-sandbox` | Executes user Python/JS code from Code Executor agent nodes inside gVisor; accepts a job over gRPC, returns stdout/stderr/value | Stateless, ephemeral fs |
| **MCP client bridge** | optional sidecar | Holds long-lived stdio/WebSocket connections to external MCP servers (§4.29 client mode); API calls into it for tool invocation | Stateful connections |
| **Relational DB** | Postgres 16 | Canonical metadata (§6) | Stateful |
| **Search engine** | OpenSearch 2 | Dense + sparse + metadata + KG index (§10.4) | Stateful |
| **Object store** | MinIO (S3-compat) | Source files and large derived artifacts | Stateful |
| **Cache / queue broker** | Redis 7 | Sessions, rate limits, work queues, scheduler lease | Stateful |

**Why these boundaries:**
- API must stay cold-fast and crash-safe; parsing and agent runs are
  long-running and must not block the request loop → separate Worker.
- Sandbox is a security boundary; must run in a different container
  image + reduced privileges → separate process, always.
- Scheduler is a separate process so API replicas can be freely scaled
  without double-firing crons. Leader-election via Redis `SET NX PX`.

---

## 3. Data Stores — Why Each

| Store | Used for | Reasoning |
|---|---|---|
| **Postgres** | All of §6 except vectors/sparse: Tenant, User, Team, ApiKey, Provider, Collection, Document, Chunk (metadata rows), Assistant, Session, Message, Agent, AgentRun, Memory (metadata), Connector, Pipeline, AuditEvent | Transactional, rich query, JSONB for flexible attrs, plentiful ops tooling. Pluggable behind `RelationalStore` port so MySQL/OceanBase can swap in (§10.5). |
| **OpenSearch** | Per-tenant, per-collection indices carrying: `dense_vector` for chunk embedding, `rank_features` or BM25 for sparse terms, typed metadata fields, highlight support, KG entity index, summary-tree index | One engine for dense + sparse + metadata avoids a separate vector DB. Pluggable behind `SearchEngine` port (§10.4). |
| **MinIO / S3** | Source file bytes (immutable, content-addressable), large derived artifacts (transcription audio, exported agent JSON, published-widget assets) | Cheap, horizontally scalable, decoupled lifecycle. Pluggable behind `ObjectStore` port (§10.6). |
| **Redis** | Session cache (ephemeral), rate limit counters, work queues (list or streams), SSE fan-out for multi-replica streaming, scheduler lock, short-lived signed tokens for embed widget | One commodity in-memory store for all ephemeral needs. Pluggable behind `Cache`/`Queue` ports (§10.7). |

Vector storage choice rationale: storing embeddings inside OpenSearch
(decision item 15) keeps retrieval to a single query — no fan-out to a
separate vector DB plus metadata DB — and simplifies tenant partitioning
via index-per-tenant-per-collection naming.

---

## 4. Public API Surface

- **HTTP REST** under `/v1` per §5. Envelope `{code, message, data}`.
- **SSE** for streaming: `/v1/assistants/{id}/sessions/{sid}/messages`
  and `/v1/agents/{id}/runs` emit events `message.delta`, `tool.call`,
  `reference`, `node.start`, `node.output`, `node.error`, `usage`,
  `done` (§8.4, §9.3).
- **OpenAI-compat** at `/v1/assistants/{id}/openai/chat/completions`,
  `/v1/agents/{id}/openai/chat/completions`, plus `/v1/models` (lists
  assistants/agents as model ids) and `/v1/embeddings` (proxy, per
  decision item 13). Tool-calls + streaming supported.
- **Webhook** triggers at `/v1/agents/{id}/webhooks/{hook}` — HMAC-
  signed header `X-OmniAI-Signature` + 5-minute replay window (decision
  item 7).
- **MCP server** endpoints exposed under `/v1/mcp/*` and a JSON-RPC
  endpoint at `/mcp` speaking the MCP protocol so external MCP clients
  can discover tools (§4.29, §5.14).
- **Metrics** at `/metrics` (Prometheus). **Health** at `/livez`,
  `/readyz`. **Traces** via OTel OTLP exporter when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- **Auth:** Bearer API keys for machine calls; session cookies + JWT
  for browser calls; optional OIDC/SAML login via a pluggable
  `IdentityProvider` port (§10.9).

Rate limiting (§5.16): token-bucket in Redis keyed by API key; defaults
60 rpm general, 10 concurrent SSE streams, 1 upload in flight per
collection. Quotas surfaced at the API-key layer (decision item 12).

Idempotency: `Idempotency-Key` on POST, 24-hour dedupe window, stored
in Redis with the first-response body (§5.17).

---

## 5. Frontend Architecture

- **Single-page app**, TypeScript + React 18 + Vite. Served as static
  assets by the API process at `/` (no separate frontend server in
  prod; dev uses `vite dev` with an API proxy).
- **Routing:** React Router v6. Screens S1–S18 from §14 map to route
  groups (`/login`, `/home`, `/knowledge`, `/knowledge/:id`,
  `/chat/:assistantId?`, `/agents`, `/agents/:id/builder`, `/search`,
  `/admin`, `/profile`, `/providers`, `/connectors`, `/memory`).
- **State:** TanStack Query for server cache; Zustand for ephemeral UI
  state (drawer open, agent canvas selection, streaming buffers). No
  global Redux store.
- **Styling:** Tailwind CSS with a design-token layer; Radix primitives
  for accessible components. WCAG 2.1 AA and RTL via `dir="rtl"`
  attribute toggle. Dark/light via CSS vars on `<html data-theme>`.
- **Agent canvas:** React Flow for the node graph; node renderers and
  the per-node inspector live under `features/agents/builder/nodes/` —
  adding a node type = adding one directory.
- **Streaming:** native `EventSource` wrapped in a typed
  `useSseStream` hook with backpressure and reconnect.
- **i18n:** i18next with per-locale JSON bundles under
  `src/i18n/<locale>.json`. Adding a locale = adding one file + one
  registry entry (§4.32).
- **Testing:** Vitest + Testing Library for unit; Playwright for the
  end-to-end AT-01…AT-20 scenarios that need a browser.

---

## 6. Plugin / Extension Points

Each is a registry keyed by a short string. All defined in code under
`backend/omniai/plugins/<kind>/` and auto-loaded at startup.

| Registry | Items shipped in MVP | How to add |
|---|---|---|
| `chunk_templates` | `general`, `qa`, `manual`, `paper`, `law`, `presentation`, `table`, `email`, `picture`, `one` (§4.4) | Implement `ChunkTemplate` interface; register by name |
| `parsers` | `pdf`, `docx`, `pptx`, `xlsx`, `csv`, `txt`, `md`, `html`, `eml`, `image`, `video` (§4.3) | Implement `DocumentParser` interface |
| `pipeline_stages` | `source`, `extract`, `chunk`, `enrich`, `embed`, `index` (§4.5) | Implement `PipelineStage` interface |
| `llm_providers` | `openai_compat`, `anthropic`, `ollama` (§10.1 — rest deferred) | Implement `LLMProvider` interface |
| `embedding_providers` | `openai_compat`, `ollama` (§10.2) | Implement `EmbeddingProvider` interface |
| `reranker_providers` | `cross_encoder_local`, `openai_compat` (§10.3) | Implement `RerankerProvider` interface |
| `asr_providers` | `whisper_local` (faster-whisper) | Implement `ASRProvider` interface |
| `tts_providers` | `piper_local` | Implement `TTSProvider` interface |
| `search_engines` | `opensearch` (+ `elasticsearch`, `infinity` stubs) (§10.4) | Implement `SearchEngine` interface |
| `relational_stores` | `postgres` (+ `mysql`, `oceanbase` stubs) (§10.5) | Implement `RelationalStore` interface — trivial since SQLAlchemy handles dialects |
| `object_stores` | `s3_compatible` (covers MinIO/S3/OSS/GCS via S3 API) + `azure_blob` (§10.6) | Implement `ObjectStore` interface |
| `caches` | `redis` (§10.7) | Implement `Cache` interface |
| `connectors` | `local_folder` reference only (§10.8 — rest deferred per decision item 2) | Implement `Connector` interface |
| `auth_providers` | `local_password`, `oidc`, `saml` (§10.9) | Implement `IdentityProvider` interface |
| `sandbox_runners` | `gvisor`, `local` (dev only) (§11.1 `SANDBOX_KIND`) | Implement `SandboxRunner` gRPC client |
| `agent_node_types` | Start, End, Retrieval, Generate, Code, Iteration, Switch, Aggregator, ListOp, Message, UserFeedback, Keyword, ExternalSearch, ToolInvocation, WebhookTrigger, Chart (§4.14) | Implement `AgentNode` interface; register a React renderer |
| `mcp_tool_providers` | `collection_tool`, `agent_tool` (server mode) + external-server client | Implement `MCPToolProvider` |

Feature flags in `config.yaml` allow entire registries to be disabled
(e.g., `features.voice: false` drops ASR/TTS entirely).

---

## 7. Dependency Direction

```
                  +-------------------+
                  |  Interfaces       |  (HTTP, SSE, MCP, CLI, UI)
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |  Application      |  (use-cases, orchestration,
                  |  (services)       |   tenant guard, transactions)
                  +---------+---------+
                            |
                            v
                  +-------------------+
                  |  Domain Core      |  (entities, value objects,
                  |                   |   policies, invariants)
                  +---------+---------+
                            ^
                            |
                  +---------+---------+
                  |  Ports            |  (abstract interfaces only)
                  +---------+---------+
                            ^
                            |
                  +-------------------+
                  |  Adapters         |  (Postgres, OpenSearch, MinIO,
                  |                   |   Redis, provider SDKs, gVisor)
                  +-------------------+
```

Domain never imports adapters. Adapters implement ports. Interfaces
wire adapters into application services at startup via a small DI
container (`dependency-injector` or hand-rolled factories).

---

## 8. Tenant Isolation

- Every service method takes `ctx: TenantContext` as its first arg.
- Repository constructors require `TenantContext` and append
  `tenant_id = ctx.tenant_id` to every query.
- OpenSearch indices are named `omniai-<tenant_id>-<collection_id>-
  chunks` etc.; no cross-tenant index queries are constructible.
- Object-store keys are prefixed `tenants/<tenant_id>/...`.
- API-key verification produces the `TenantContext`; no code path
  constructs one from a raw request field.
- Audit log records `(actor, tenant_id, action, target)` for every
  privileged action (§12.7, AT-07).

---

## 9. Observability

- **Logging:** `structlog` JSON; bound fields: `correlation_id`
  (generated at the HTTP edge), `tenant_id`, `user_id`, `route`,
  `span_id`. Worker jobs carry the correlation_id through the queue
  payload.
- **Metrics:** Prometheus. Counters/histograms declared in
  `omniai.observability.metrics` and imported where raised. Required
  per §12.6 and AT-19: request count/latency per route, parse success
  rate, queue depth, tokens in/out per provider, SSE stream count,
  rate-limit rejections.
- **Traces:** OpenTelemetry auto-instrumentation for FastAPI, SQLA,
  httpx, redis; manual spans around worker stages so a single chat
  turn shows `retrieve` → `rerank` → `llm_call` (AT-19).
- **Error reporting:** optional Sentry DSN via env var.

---

## 10. Security Posture

- TLS termination at the edge (ingress / reverse proxy); internal TLS
  is optional and governed by `INTERNAL_TLS=true`.
- Secrets (provider keys, webhook secrets, SSO client secrets) live in
  Postgres encrypted with a deployment `ENCRYPTION_KEY` (AES-GCM
  envelope).
- API keys stored as bcrypt/argon2 hashes; raw value shown once.
- Webhook HMAC signatures (`X-OmniAI-Signature`), 5-minute clock skew
  tolerance, replay nonce recorded in Redis (decision item 7).
- Sandbox: gVisor sandbox, no network except allowlisted egress per
  agent node, tmpfs only, CPU/mem/time caps, Python stdlib minus
  `os/subprocess/ctypes/socket` (except when network is granted),
  third-party pinned to `requests/httpx/pandas/numpy/pydantic`
  (decision item 14).
- Dependency scanning (`pip-audit`) and Docker image scanning
  (`trivy`) enforced in CI.

---

## 11. Deployment Layout

### 11.1 Docker Compose (dev + small prod)
`deploy/compose/docker-compose.yml` — services: `api`, `worker`,
`scheduler`, `sandbox`, `postgres`, `opensearch`, `minio`, `redis`.
Override files under `deploy/compose/overrides/` for dev (hot reload,
mount source) and prod (replicas, resource limits).

### 11.2 Kubernetes Helm chart
`deploy/helm/omniai/` — one chart, one values file, separate Deployments
for `api`, `worker`, `scheduler`, `sandbox`; dependencies on operator-
managed or external Postgres/OpenSearch/MinIO/Redis via subcharts or
externalName Services. HorizontalPodAutoscaler on `api` and `worker`.
PodDisruptionBudgets. NetworkPolicies to restrict sandbox egress.

### 11.3 Image strategy
- `omniai/api:<version>` — FastAPI + built UI assets.
- `omniai/worker:<version>` — worker + parser dependencies (heavier:
  tesseract, ffmpeg, faster-whisper).
- `omniai/sandbox:<version>` — minimal Python/Node + gVisor hooks.
- Slim and full variants per F62; multi-arch x86_64 + arm64 per F61
  (decision item 20).

---

## 12. Module Structure — Backend

```
backend/
├── pyproject.toml
├── README.md
├── omniai/
│   ├── __init__.py
│   ├── bootstrap/            # app factory, DI wiring, plugin discovery
│   ├── config/               # pydantic-settings, config.yaml loader
│   ├── domain/               # pure entities & value objects (no I/O)
│   │   ├── knowledge/        # Collection, Document, Chunk, KGNode, SummaryTreeNode
│   │   ├── assistants/       # Assistant, Session, Message
│   │   ├── agents/           # Agent, AgentRun, Graph, Node, Port
│   │   ├── memory/           # Memory scopes & records
│   │   ├── providers/        # Provider descriptor + capability vocabulary
│   │   ├── tenants/          # Tenant, User, Team, ApiKey, Role
│   │   ├── pipelines/        # Pipeline, Stage descriptors
│   │   └── connectors/       # Connector descriptor
│   ├── ports/                # Abstract interfaces (no implementation)
│   │   ├── relational.py
│   │   ├── search_engine.py
│   │   ├── object_store.py
│   │   ├── cache.py
│   │   ├── llm_provider.py
│   │   ├── embedding_provider.py
│   │   ├── reranker_provider.py
│   │   ├── asr_provider.py
│   │   ├── tts_provider.py
│   │   ├── auth_provider.py
│   │   ├── sandbox_runner.py
│   │   ├── connector.py
│   │   ├── document_parser.py
│   │   ├── chunk_template.py
│   │   ├── pipeline_stage.py
│   │   ├── mcp.py
│   │   └── agent_node.py
│   ├── application/          # use-cases (orchestration, transactions)
│   │   ├── knowledge_service.py
│   │   ├── document_service.py
│   │   ├── parsing_service.py
│   │   ├── retrieval_service.py
│   │   ├── assistant_service.py
│   │   ├── session_service.py
│   │   ├── agent_service.py
│   │   ├── agent_runtime.py  # executes agent graphs
│   │   ├── memory_service.py
│   │   ├── provider_service.py
│   │   ├── tenant_service.py
│   │   ├── api_key_service.py
│   │   ├── connector_service.py
│   │   ├── pipeline_service.py
│   │   └── admin_service.py
│   ├── adapters/             # concrete implementations of ports
│   │   ├── relational/
│   │   │   ├── postgres/     # SQLA models, migrations, repositories
│   │   │   └── mysql/        # stub
│   │   ├── search/
│   │   │   └── opensearch/
│   │   ├── object_store/
│   │   │   ├── s3_compatible/
│   │   │   └── azure_blob/
│   │   ├── cache/
│   │   │   └── redis/
│   │   ├── sandbox/
│   │   │   └── gvisor/
│   │   └── mcp/
│   │       ├── server/
│   │       └── client/
│   ├── plugins/              # registries — one sub-dir per plugin kind
│   │   ├── parsers/{pdf,docx,pptx,xlsx,csv,txt,md,html,eml,image,video}/
│   │   ├── chunk_templates/{general,qa,manual,paper,law,presentation,table,email,picture,one}/
│   │   ├── pipeline_stages/{source,extract,chunk,enrich,embed,index}/
│   │   ├── llm_providers/{openai_compat,anthropic,ollama}/
│   │   ├── embedding_providers/{openai_compat,ollama}/
│   │   ├── reranker_providers/{cross_encoder_local,openai_compat}/
│   │   ├── asr_providers/{whisper_local}/
│   │   ├── tts_providers/{piper_local}/
│   │   ├── connectors/{local_folder}/
│   │   ├── auth_providers/{local_password,oidc,saml}/
│   │   └── agent_nodes/{start,end,retrieval,generate,code,iteration,switch,aggregator,list_op,message,user_feedback,keyword,external_search,tool_invocation,webhook_trigger,chart}/
│   ├── interfaces/           # inbound adapters
│   │   ├── http/
│   │   │   ├── app.py        # FastAPI factory
│   │   │   ├── deps.py       # auth, tenant, rate-limit deps
│   │   │   ├── envelope.py   # {code,message,data} helper
│   │   │   ├── errors.py     # exception → HTTP status mapping
│   │   │   ├── sse.py        # SSE response helpers
│   │   │   └── routes/
│   │   │       ├── collections.py
│   │   │       ├── documents.py
│   │   │       ├── chunks.py
│   │   │       ├── metadata.py
│   │   │       ├── retrieve.py
│   │   │       ├── assistants.py
│   │   │       ├── sessions.py
│   │   │       ├── openai_compat.py
│   │   │       ├── agents.py
│   │   │       ├── memory.py
│   │   │       ├── providers.py
│   │   │       ├── users.py
│   │   │       ├── teams.py
│   │   │       ├── tenants.py
│   │   │       ├── api_keys.py
│   │   │       ├── connectors.py
│   │   │       ├── admin.py
│   │   │       └── mcp.py
│   │   ├── cli/              # Typer-based admin CLI (F63)
│   │   ├── mcp_server/       # MCP JSON-RPC server
│   │   └── webhook/          # signed-webhook receiver
│   ├── workers/              # Celery/Arq tasks
│   │   ├── worker.py         # entry point
│   │   ├── parsing.py
│   │   ├── embedding.py
│   │   ├── indexing.py
│   │   ├── graph_build.py
│   │   ├── summary_tree.py
│   │   ├── connector_sync.py
│   │   └── agent_driver.py   # executes long-running agent runs
│   ├── scheduler/            # cron + lease
│   ├── observability/
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   └── tracing.py
│   ├── security/
│   │   ├── hashing.py
│   │   ├── jwt.py
│   │   ├── secrets.py        # envelope encryption
│   │   └── hmac.py           # webhook signatures
│   └── testing/              # shared test fixtures & fakes
├── tests/
│   ├── unit/
│   ├── integration/          # hits real Postgres/OpenSearch/MinIO via docker
│   └── acceptance/           # AT-01…AT-20 scenarios
└── scripts/                  # dev utilities
```

**Delete-a-feature examples.**
- Remove KG: delete `plugins/agent_nodes/...` nothing (not there); delete
  `workers/graph_build.py`, `interfaces/http/routes/collections.py`'s
  `/graph/*` handlers, `application/*` KG calls, and set
  `features.knowledge_graph: false`. Nothing else breaks.
- Remove voice: delete `plugins/asr_providers/`, `plugins/tts_providers/`,
  flip `features.voice: false`; `/v1/providers` no longer accepts
  `kind=asr|tts`.
- Remove a connector: delete `plugins/connectors/<name>/`.

---

## 13. Module Structure — Frontend

```
frontend/
├── package.json
├── vite.config.ts
├── index.html
├── src/
│   ├── main.tsx
│   ├── app/                  # router, providers, error boundary
│   ├── api/                  # typed clients generated from OpenAPI
│   ├── config/               # runtime env, feature flags fetched from /v1/config
│   ├── auth/                 # login, tokens, role gates
│   ├── components/           # generic primitives (Button, Modal, Toast…)
│   ├── layout/               # AppShell, SideNav, TopBar, CommandPalette
│   ├── hooks/                # useSseStream, useTenant, useToast…
│   ├── i18n/                 # i18next init + per-locale JSON
│   ├── theme/                # tokens, dark/light, RTL
│   ├── features/
│   │   ├── home/             # S2
│   │   ├── auth/             # S1
│   │   ├── knowledge/        # S3, S4, S5, S6, S7
│   │   │   ├── list/
│   │   │   ├── detail/
│   │   │   ├── documents/
│   │   │   ├── parse-view/
│   │   │   ├── retrieval-test/
│   │   │   ├── graph/
│   │   │   └── metadata/
│   │   ├── chat/             # S8
│   │   │   ├── conversation/
│   │   │   ├── citations/
│   │   │   ├── voice/
│   │   │   ├── tts/
│   │   │   ├── compare/
│   │   │   └── thinking/
│   │   ├── assistants/       # S9
│   │   ├── search/           # S13
│   │   ├── agents/           # S10, S11, S12
│   │   │   ├── list/
│   │   │   ├── builder/
│   │   │   │   ├── canvas/   # React Flow wrapper
│   │   │   │   ├── palette/
│   │   │   │   ├── inspector/
│   │   │   │   ├── variables/
│   │   │   │   └── nodes/    # one renderer dir per node type
│   │   │   └── run/
│   │   ├── memory/           # S18
│   │   ├── admin/            # S14
│   │   ├── profile/          # S15
│   │   ├── providers/        # S16
│   │   ├── connectors/       # S17
│   │   └── widget/           # embeddable iframe app (separate bundle)
│   └── test/                 # Vitest setup
├── e2e/                      # Playwright specs for AT-01…AT-20 UI flows
└── public/                   # static assets (favicons, locale flags)
```

Every `features/<name>/` is deletable: removing the directory plus its
route registration removes the feature entirely.

---

## 14. Cross-Cutting Flows

### 14.1 Chat Turn (§4.9, AT-01, AT-05)
1. Client POSTs message → API route `assistants.send_message`.
2. Service loads assistant + session; asserts tenant match.
3. Optional query-rewrite (LLM call, cached) via `QueryRewriter`.
4. `RetrievalService.retrieve(...)`:
   - Dense + sparse on OpenSearch, fused by weight.
   - Optional rerank via `RerankerProvider`.
   - Optional KG/TOC expansion, metadata filter.
5. Context packer builds numbered references `[n]`.
6. `LLMProvider.chat(stream=True)` yields deltas; API forwards as SSE.
7. `CitationMapper` scans accumulated text, emits `reference` events.
8. Final `usage` + `done` events; message persisted with references
   and token counts.

### 14.2 Document Ingest (§4.5, §7)
1. API `documents.upload` writes bytes to object store + row in
   Postgres (`status=PENDING`, `contentHash` computed).
2. `parsing_service.start_parse` enqueues `parse_document(doc_id,
   version)` on Redis; returns immediately.
3. Worker picks up; runs the pipeline stages in order, updating status
   (`PARSING` → `EMBEDDING` → `INDEXING` → `READY`). Each stage is
   idempotent keyed on `(doc_id, version, stage)`.
4. Chunk rows written to Postgres; dense vectors + sparse features +
   metadata indexed in OpenSearch under the collection index.
5. Events `document.status_changed` published to Redis pub/sub so the
   UI updates live.

### 14.3 Agent Run (§9.3, AT-08, AT-09)
1. Trigger: HTTP POST or webhook or schedule → `AgentRun` row,
   `status=QUEUED`.
2. `agent_driver` worker loads the graph, walks from `Start`, pushing
   node jobs onto a per-run mini-scheduler.
3. Each node type is executed by its registered handler; outputs stored
   in the run's variable map; events streamed via Redis to SSE clients.
4. Code nodes dispatch to the `sandbox` service over gRPC; results
   returned; timeouts/errors recorded.
5. `End` node closes the run; final `done` event with usage + output.

---

## 15. Testing Strategy

- **Unit** (pytest, no I/O): domain entities, pure services, plugin
  implementations using fakes for ports.
- **Integration** (pytest + testcontainers): adapters against real
  Postgres/OpenSearch/MinIO/Redis spun up per session.
- **Acceptance** (pytest + httpx + Playwright): one file per AT-xx
  scenario in §15; test names embed the AT id. These are the ship gate.
- **Contract**: OpenAPI schema generated from FastAPI is diffed against
  `docs/openapi.yaml` in CI to catch unintended API drift.
- **Frontend**: Vitest unit tests next to components; Playwright E2E
  shares fixtures with backend acceptance suite (seeded via a test-only
  `/v1/testing/seed` endpoint gated by env flag).

---

## 16. Build, CI, Versioning

- **Monorepo** with `backend/` and `frontend/`. Root `Makefile`
  orchestrates common tasks (`make dev`, `make test`, `make images`).
- **CI (GitHub Actions or GitLab CI — TBD by ops):**
  lint → unit → integration → build UI → package images → run
  acceptance suite against compose stack → publish images + SBOM.
- **Versioning:** semantic; a single version for the product; backend
  and frontend released as a set.
- **Migrations:** Alembic for Postgres, managed via `omniai-cli db
  upgrade`. OpenSearch index templates versioned under
  `adapters/search/opensearch/templates/`.

---

## 17. Traceability Snapshot

| Spec artifact | Module(s) |
|---|---|
| §4.1 F1 Collection | `domain/knowledge`, `application/knowledge_service`, `routes/collections` |
| §4.2–4.3 F2/F3 | `routes/documents`, `application/document_service`, `plugins/parsers/*` |
| §4.4 F4 chunking | `plugins/chunk_templates/*` |
| §4.5 F5 pipeline | `application/parsing_service`, `workers/parsing,embedding,indexing`, `plugins/pipeline_stages/*` |
| §4.9 F9 chat | `application/assistant_service`, `routes/assistants,sessions`, `interfaces/http/sse` |
| §4.10 retrieval | `application/retrieval_service`, `adapters/search/opensearch` |
| §4.11 providers | `application/provider_service`, `plugins/llm_providers,embedding_providers,reranker_providers` |
| §4.14 agent builder | `domain/agents`, `application/agent_service,agent_runtime`, `plugins/agent_nodes/*`, `frontend/features/agents/builder` |
| §4.29 MCP | `adapters/mcp/*`, `interfaces/mcp_server`, `routes/mcp` |
| §6 data model | `adapters/relational/postgres/models` + `domain/*` |
| §12 NFRs | `observability/*`, `security/*`, Helm `hpa`/`pdb` |
| §14 UI | `frontend/features/*` screens |
| §15 ATs | `tests/acceptance/at_*.py` + `e2e/at_*.spec.ts` |

---

## 18. Locked Defaults Recap (from `SPEC_SUMMARY.md`)

1. Extended features shipped iteratively after M10 unless earlier AT
   requires them (KG M7+, Summary Tree M7+, MCP M9+).
2. M9 ships the Connector interface + `local_folder` reference; other
   21 connectors = future plugins.
3. 3 reference LLM adapters (OpenAI-compat, Anthropic, Ollama); others
   = future plugins.
4. Voice = interface + local ASR (faster-whisper) + local TTS (Piper)
   for dev.
5. Chunk edits versioned + soft-delete.
6. Agent-run retention default 90 days, per-tenant overridable.
7. Webhooks = HMAC header, 5-min replay window, per-hook secret.
8. Publishing = no review; publish = immediately public within tenant.
9. Fusion = linear weighted combination of normalized scores.
10. Cross-collection topK = global fused score.
11. Re-parse = old chunk ids kept as tombstones; prior answers banner.
12. Cross-language reply in original query language.
13. OpenAI-compat = `/chat/completions` + tool calls + `/v1/models`
    + `/v1/embeddings`; `/v1/images` deferred.
14. Sandbox stdlib allowlist as proposed.
15. Embeddings stored inside OpenSearch.
16. Parent-child via `parentChunkId` to aux context chunks.
17. Ingestion pipelines = linear stages (DAG upgrade later if needed).
18. Model-comparison (up to 3 side-by-side) in M4.
19. KG UI browser in M7 or later.
20. Multi-arch x86_64 + arm64 images from day one.
21. GPU off by default; deep-layout parsing/local models require
    explicit `GPU_ENABLED=true`.

---

*End of ARCHITECTURE.md — awaiting approval before `MILESTONES.md`.*
