# SPEC.md — Clean-Room Behavioral Specification

> Vendor-neutral product specification for a functionally equivalent re-implementation
> of a Retrieval-Augmented Generation (RAG) platform. No source code has been quoted
> or paraphrased. All names are spec-local.

---

## 1. Product Overview

The product is a self-hostable **knowledge platform** that ingests unstructured and
semi-structured documents from many sources, turns them into a searchable grounded
context store, and lets users ask natural-language questions that are answered by a
pluggable large language model (LLM). Answers cite the exact passages they came
from. The same platform also lets users visually compose **agents and workflows**
that combine retrieval, tool use, code execution, and multi-step reasoning.

**Target users**
- Knowledge workers who need to query private document collections.
- Developers integrating a grounded QA layer into their own applications.
- Administrators running a shared internal RAG service for a team or organization.
- Workflow builders automating document-centric business processes.

**Primary value proposition**
Deep, trustworthy answers over private data — complete with verifiable citations —
without writing pipeline code, and with a visual builder for multi-step AI
workflows.

**Competitive positioning**
Combines three capabilities that usually require stitching several tools together:
(1) deep document understanding for messy real-world files, (2) a production
retrieval stack with hybrid search and reranking, (3) a visual agent/workflow
builder. Self-hosted, multi-tenant, model-agnostic.

---

## 2. Feature Inventory

See the confirmed inventory (74 items, Core / Standard / Extended). Reproduced and
referenced by number throughout Sections 4 and 14.

**Core (1–19):** Knowledge Collection, Document Upload, Multi-Format Ingestion,
Chunking Templates, Parsing Pipeline Execution, Chunk Review & Edit, Embedding
Model Selection, Retrieval Testing Panel, Chat Assistant, Grounded Answers with
Citations, Hybrid Retrieval, Reranking Stage, LLM Provider Management, Streaming
Responses, Conversation Memory, User Account & Login, Tenant/Team Isolation,
HTTP REST API, API Key Management.

**Standard (20–52):** Team Collaboration, Admin Dashboard, Assistant System Prompt
Editor, Assistant Model Comparison, Voice Input, TTS Output, AI Search Page,
Cross-Language Retrieval, Parent-Child Chunking, GraphRAG Indexing, Hierarchical
Summarization Index, Auto-Tagging, Per-File Metadata, Document TOC, Keyword
Weighting, Agent Builder, Agent Component Library, Agent Memory, Agent Sessions,
Agent Templates, Agent Versioning, Agent Publishing, Agent Webhook Triggers,
Structured Output, Sandbox Code Execution, Chart Generation, External Data
Connectors, OpenAI-Compatible API, Assistant Embed Widget, Registration Policy,
Dark Mode, Multi-Language UI, Mobile-Responsive UIs.

**Extended (53–74):** MCP Server Mode, MCP Client Mode, Pluggable Document Parser,
Pluggable Vector/Index Engine, Pluggable Relational Store, Pluggable Object Store,
Pluggable Cache, Kubernetes Deployment, ARM64 Support, Slim/Full Docker Images,
Admin CLI, Task Executor Monitoring, Image Display in Chat, HTML File Preview,
Orchestratable Ingestion Pipelines, Manual GraphRAG/RAPTOR Rebuild, Benchmarking
Hooks, Web-Search-Augmented Chat, Deep Research Mode, Reasoning Display,
Team-Shared Agents, Public Share Links.

---

## 3. User Personas & Journeys

### P1 — Knowledge Worker "Ada"
Uploads reports and answers questions from them.
1. Signs up, logs in.
2. Creates a Knowledge Collection called "Policies".
3. Uploads 50 PDFs and DOCX files.
4. Picks the default chunking template and an embedding model, clicks Parse.
5. Watches per-file progress. When done, opens one file to spot-check chunks.
6. Creates a Chat Assistant bound to "Policies", sets a short system prompt.
7. Asks questions, reads answers, clicks citations to see the original pages.

### P2 — Developer "Bao"
Embeds the QA service into his own app.
1. Generates an API key in Profile → API Keys.
2. Creates the collection via HTTP, uploads files via HTTP, triggers parse.
3. Polls document status until READY.
4. Calls the OpenAI-compatible chat endpoint from his app.
5. Renders citations in his own UI using the structured reference payload.

### P3 — Admin "Chidi"
Operates the platform for a 200-person company.
1. Deploys via Kubernetes Helm chart, points it at managed Postgres, S3, and
   Elasticsearch services.
2. Registers LLM providers (hosted + on-prem Ollama).
3. Turns off open registration. Invites users into the admin tenant.
4. Creates teams, assigns members.
5. Monitors parsing workers and disk usage from the Admin Dashboard.

### P4 — Workflow Builder "Dana"
Builds an agent that drafts weekly competitive briefs.
1. Opens Agent Builder, starts from the "Deep Research" template.
2. Rewires a Retrieval node to point at the "Competitors" collection.
3. Adds a Code node that pulls RSS and massages the result.
4. Connects a Generate node with structured JSON output.
5. Tests with the run panel, publishes as a shareable app, schedules a webhook.

### P5 — End User "Eun"
Uses a chat widget embedded on her company's internal wiki.
1. Types a question into the widget.
2. Gets a streamed, cited answer.
3. Clicks a citation; a side pane opens the source document.

### P6 — Data Steward "Farah"
Keeps the knowledge base fresh and correct.
1. Opens a collection, filters documents by metadata ("owner = legal").
2. Re-runs parsing on files that changed.
3. Edits a misleading chunk; adds keywords to improve findability.
4. Runs a retrieval test with common queries to confirm quality.

---

## 4. Functional Specification

Features are described at the observable level: inputs, outputs, behavior, edge
cases, acceptance criteria.

### 4.1 Knowledge Collection (F1)
**Purpose:** Group related documents so they can be searched together and bound to
an assistant or agent.
**Inputs:** name (1–128 chars, unique within tenant), optional description, avatar
image, language, visibility (private/tenant-shared), default chunking template,
embedding model reference, retrieval defaults.
**Outputs:** Collection record with a stable identifier, creation timestamp,
aggregate counts (docs, chunks, tokens), last activity time.
**Behavior:** Creation yields an empty collection. Rename updates display only;
identifier is immutable. Delete removes all documents, chunks, and derived indices
and frees storage asynchronously. Two collections in the same tenant may not share
a name.
**Edge cases:** Duplicate name → 409. Delete while parsing in progress → parsing
jobs are cancelled. Changing embedding model after content exists → requires full
re-index; system warns and blocks until confirmed.
**Acceptance:**
- Create, list, update, delete succeed and reflect within 1s.
- Aggregate counts update after parsing completes.
- Cross-tenant access returns 404.

### 4.2 Document Upload (F2)
**Purpose:** Add source material to a collection.
**Inputs:** multipart file(s) up to a configurable per-file size cap (default
128 MB) and per-request count cap (default 64). Optional per-file metadata map.
**Outputs:** Per-file record with id, name, size, MIME, status=PENDING.
**Behavior:** Accepted files are stored verbatim in the object store and registered
in the catalog. No parsing happens automatically unless the collection is in
"parse-on-upload" mode.
**Edge cases:** Unknown MIME → stored but marked UNSUPPORTED; file over cap →
rejected with a clear error; duplicate file by content hash → optional dedupe
mode returns the existing id.
**Acceptance:** Uploaded files are listed immediately; binary download returns
the exact bytes.

### 4.3 Multi-Format Ingestion (F3)
**Purpose:** Convert diverse source files into plain text plus structure
(headings, tables, images, speaker turns, etc.).
**Supported inputs and what is extracted:**
- **PDF** — text, layout blocks, tables as row/col grids, images with captions,
  page numbers; optional OCR for scanned PDFs.
- **DOC / DOCX** — text, headings, tables, inline images with order preserved.
- **PPT / PPTX** — per-slide text, speaker notes, titles, images.
- **XLS / XLSX / CSV / TSV** — per-sheet tables; each row optionally a chunk.
- **TXT** — raw text, split by paragraph.
- **MD / MDX** — headings, code blocks, tables.
- **HTML** — main content extracted; boilerplate removed; tables preserved.
- **EML / MBOX** — headers, body (HTML or text), attachments recurse.
- **Images (JPG/PNG/TIF/GIF)** — OCR text + optional VLM description.
- **Video** — transcript via speech-to-text with timecodes; key-frame captions.
**Outputs:** ordered list of typed content blocks bound to a document.
**Edge cases:** Encrypted PDFs → marked FAILED with reason; zero-text scans → OCR
triggered; very large files streamed in pages.
**Acceptance:** For each supported format, a representative fixture produces
non-empty structured blocks.

### 4.4 Chunking Templates (F4)
**Purpose:** Turn extracted content into retrievable units appropriate to the
document kind.
**Available templates (user-selectable per collection or per file):**
- **General** — paragraph-aware, target ~500 tokens, overlap optional.
- **Q&A** — detects question/answer pairs; each pair is one chunk.
- **Manual / Book** — chapter/section aware with parent-chunk pointers.
- **Paper** — title/abstract/section/reference-aware.
- **Law** — article- and clause-aware.
- **Presentation** — one slide = one chunk.
- **Table** — one row = one chunk, with column headers embedded.
- **Email** — one message = one chunk; thread context retained.
- **Picture** — OCR/VLM text as one chunk with image reference.
- **One** — whole document as a single chunk.
**Outputs:** chunks with id, text, ordinal, parent id (optional), positions
(page, bbox or line range), image refs, auto keywords, auto questions.
**Edge cases:** Chunks over a max token limit are split. Empty chunks are
dropped. Changing template re-chunks the file.
**Acceptance:** For each template, a golden document produces a deterministic
chunk count within ±5%.

### 4.5 Parsing Pipeline (F5, F67)
**Stages (black-box):**
1. **Fetch** — pull bytes from object store.
2. **Extract** — format-specific extraction → structured blocks.
3. **Chunk** — template-specific splitting.
4. **Enrich** — optional auto-tagging, TOC generation, metadata inference.
5. **Embed** — call embedding provider in batches; cache by content hash.
6. **Index** — write vector + sparse + metadata entries to the search engine.
**Guarantees:** At-least-once processing with idempotent writes keyed on document
version. Visible status transitions: PENDING → PARSING → EMBEDDING →
INDEXING → READY / FAILED / CANCELLED.
**Custom pipelines:** users can compose pipelines from typed stages (Source,
Transformer, Chunker, Enricher, Embedder, Sink) and bind them to a collection.

### 4.6 Chunk Review & Edit (F6)
Users see a paginated list of chunks per document with their original positions
highlighted. They can edit text, toggle enabled/disabled (disabled chunks are
excluded from retrieval), attach keywords/questions (used for recall boosting),
and delete chunks. Edits trigger re-embedding of the affected chunk only.

### 4.7 Embedding Model Selection (F7)
Collection-level setting. Choosing a model at create-time is required; changing
later forces re-embed of all chunks. The platform exposes a managed list of
registered models per tenant.

### 4.8 Retrieval Testing Panel (F8)
Given a query, collection list, and retrieval parameters, return the top-K chunks
with similarity scores, highlights, the document each came from, and the exact
retrieval settings used. Useful for tuning without invoking an LLM.

### 4.9 Chat Assistant (F9, F10, F15, F22, F23)
**Purpose:** Answer user questions using one or more collections.
**Inputs:** assistant id, user message, optional session id.
**Config:** name, avatar, bound collections, LLM + generation params, system
prompt, empty-answer fallback text, similarity threshold, top-K, reranker on/off,
citations on/off, suggested-follow-up on/off.
**Behavior:**
1. Input is optionally rewritten using conversation history.
2. Query is sent to retrieval (hybrid dense + sparse + optional rerank).
3. Top-K chunks are formatted into the system prompt as numbered references.
4. LLM is called, streaming tokens to the client.
5. Citations in the answer are mapped back to the referenced chunks and
   surfaced to the UI/API.
6. If retrieval is empty and a fallback is set, the fallback text is returned.
**Edge cases:** No matching chunks + no fallback → concise "I don't know" reply.
LLM error → error event on stream, partial text preserved.
**Acceptance:** Every answer that cites `[n]` has a matching reference payload;
streaming closes with a final usage record.

### 4.10 Hybrid Retrieval + Rerank (F11, F12)
**Capabilities exposed:** dense vector search, sparse keyword search, and a fused
ranked list; optional second-pass cross-encoder reranker; optional knowledge
graph traversal; optional document-TOC expansion; optional metadata filter.
**Parameters:** top-K, similarity threshold, vector-vs-keyword weight, reranker
id, keyword string, highlight on/off, cross-language on/off, KG on/off,
TOC-enhance on/off, metadata condition.

### 4.11 LLM Provider Management (F13)
Admin registers providers (API base URL, API key, model ids, capabilities:
chat, embed, rerank, tts, asr, vision). Users select from registered models.
Per-tenant overrides supported.

### 4.12 User Accounts, Tenants, Teams (F16, F17, F20)
- Email + password signup (if enabled), email verification optional.
- A user belongs to exactly one primary tenant and may be invited into others.
- Roles within a team: OWNER, ADMIN, MEMBER, VIEWER.
- Resources (collections, assistants, agents, API keys) belong to a tenant.
- Cross-tenant access is never implicit.

### 4.13 HTTP API + API Keys (F18, F19)
See Section 5 for the wire contract. API keys are created per tenant, shown once
at creation, revocable, and scope-limited by the creator's role.

### 4.14 Agent Builder & Component Library (F35, F36)
**Purpose:** Compose multi-step AI workflows visually.
**Graph model:** a directed graph of typed components connected by typed ports
(text, list, json, number, image, file). Components include:
- **Start** / **End**.
- **Retrieval** — query one or more collections.
- **Generate** — LLM call with prompt template, variables, tool list,
  structured-output schema.
- **Code Executor** — Python or JavaScript in a sandbox.
- **Iteration / Loop** — run a subgraph per element of a list.
- **Switch / Branch** — conditional routing.
- **Variable Aggregator** — merge multiple branches into one.
- **List Operation** — map / filter / sort / slice.
- **Message** — emit a message to the user.
- **User Feedback / Input** — pause for human response.
- **Keyword** — extract keywords.
- **External Search** — web search via a registered provider.
- **Tool Invocation** — call a named tool (HTTP, MCP, SQL, shell-safe).
- **Webhook Trigger** — external event starts a run.
- **Chart** — render chart from data.

### 4.15 Agent Memory (F37)
Key-value + semantic memory scoped to {agent, user} or {agent, session}. Write
via explicit component or automatic extraction. Read via semantic query or
direct key lookup. Extraction runs are logged and inspectable.

### 4.16 Agent Sessions, Publishing, Sharing (F38, F41, F73, F74)
Each agent conversation is a Session with retained messages and variables. An
agent can be published as an app with a public URL and a shareable widget. Team
sharing grants specific roles to teammates.

### 4.17 Voice In / TTS Out (F24, F25)
Voice input uses a registered ASR provider to transcribe audio to text before
chat. TTS reads out responses using a selected voice; output is an audio
stream.

### 4.18 AI Search Page (F26)
Standalone page that runs retrieval over selected collections and presents ranked
passages with optional LLM-generated summary. Distinct from Chat in that no
persistent session or system prompt is required.

### 4.19 Cross-Language Retrieval (F27)
When enabled, the query is expanded into additional languages (by translation
before embedding or by a multilingual embedding) so documents in other languages
can match.

### 4.20 Parent-Child Chunking (F28)
Small chunks are used for recall; when a small chunk is selected, its parent
block (section, page, or slide) is substituted for LLM context to retain
surrounding semantics.

### 4.21 Knowledge-Graph Index (F29, F68)
Per-collection index of entities and relations extracted from chunks. Graph is
browsable in the UI, queryable during retrieval, and rebuildable on demand.

### 4.22 Hierarchical Summarization Index (F30, F68)
Builds a tree of progressively summarized clusters over the collection, enabling
long-context queries that span many documents.

### 4.23 Auto-Tagging (F31)
Each chunk gets a small number of semantic tags derived from the collection's
tag vocabulary. Tags are queryable at retrieval time.

### 4.24 File Metadata & Filtered Retrieval (F32)
Arbitrary key-value metadata per document. Queries may include a metadata
condition (equals, in, range, exists) that restricts retrieval.

### 4.25 Document TOC (F33)
Long documents get an auto-generated outline. TOC is used to expand context
around a hit and to bias ranking.

### 4.26 Keyword Weighting (F34)
Users may attach weighted keywords to chunks; keywords boost sparse-search
scoring at query time.

### 4.27 Structured Output, Sandbox Code, Charts (F43, F44, F45)
Generate nodes and assistants may declare a JSON schema; model output is parsed
and validated. Code nodes run in an isolated sandbox with resource and time
limits. A Chart node consumes tabular data and emits a chart image + spec.

### 4.28 External Data Connectors (F46)
Per-connector sync creates/updates documents in a target collection on a
schedule or on demand. Supported sources (as capability list, not mandate) are
in Section 10. Incremental and delete-propagation behavior is connector-
specific and declared per connector.

### 4.29 MCP (F53, F54)
- **Server mode:** expose each collection and each agent as an MCP tool to
  external MCP-compatible clients.
- **Client mode:** register external MCP servers; their tools become available
  to agent Tool Invocation nodes.

### 4.30 Admin Dashboard, CLI, Monitoring (F21, F63, F64)
Admin UI shows users, teams, quotas, service health (vector engine, DB, object
store, cache, workers), parsing queue depth, and usage counters. A CLI provides
the same actions for scripting.

### 4.31 Embeddable Widget / iframe (F48)
Each published assistant or agent gets an embeddable snippet (iframe) with
theming parameters. Optionally gated by a short-lived signed token.

### 4.32 Multi-Language UI + RTL (F51)
The web UI supports at least the locales listed in the inventory, including
right-to-left languages.

### 4.33 Deep-Research / Thinking Mode (F71, F72)
Chat can run an agentic loop (plan → retrieve → read → plan → …) before
responding; intermediate thoughts are shown collapsed. Web-search tool is
optional.

---

## 5. External API Specification

### 5.1 Authentication
All HTTP requests carry `Authorization: Bearer <apiKey>`. Missing or invalid →
401. Revoked keys → 401 with reason.

### 5.2 Common Response Envelope
```
{ "code": 0, "message": "ok", "data": <payload> }
```
Non-zero `code` indicates an error; `message` is human-readable; `data` may be
absent on error.

### 5.3 Resource: Collection

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/collections` | Create |
| GET | `/v1/collections` | List (paginated; filter by name, id, status) |
| GET | `/v1/collections/{id}` | Read |
| PUT | `/v1/collections/{id}` | Update |
| DELETE | `/v1/collections` | Delete by ids or all |
| POST | `/v1/collections/{id}/graph/rebuild` | Trigger KG build |
| GET | `/v1/collections/{id}/graph/status` | KG build status |
| DELETE | `/v1/collections/{id}/graph` | Delete KG |
| POST | `/v1/collections/{id}/summary-tree/rebuild` | Build summarization tree |
| GET | `/v1/collections/{id}/summary-tree/status` | Tree build status |

Create request fields: `name` (required), `description`, `avatar`,
`embeddingModel`, `chunkTemplate`, `pipelineId`, `permission` in {`private`,
`team`}, `defaults` (retrieval defaults).

### 5.4 Resource: Document

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/collections/{id}/documents` | Upload (multipart) |
| GET | `/v1/collections/{id}/documents` | List (page, pageSize, keywords, status, metadataCondition) |
| GET | `/v1/collections/{id}/documents/{docId}` | Download bytes |
| PUT | `/v1/collections/{id}/documents/{docId}` | Update (name, metadata, chunkTemplate, enabled) |
| DELETE | `/v1/collections/{id}/documents` | Delete by ids or all |
| POST | `/v1/collections/{id}/documents/parse` | Start parsing: body `documentIds` |
| POST | `/v1/collections/{id}/documents/parse/cancel` | Stop parsing |

### 5.5 Resource: Chunk

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/collections/{id}/documents/{docId}/chunks` | Insert chunk |
| GET | `/v1/collections/{id}/documents/{docId}/chunks` | List |
| GET | `/v1/collections/{id}/documents/{docId}/chunks/{chunkId}` | Read |
| PATCH | `/v1/collections/{id}/documents/{docId}/chunks/{chunkId}` | Update fields |
| PATCH | `/v1/collections/{id}/documents/{docId}/chunks` | Batch enable/disable |
| DELETE | `/v1/collections/{id}/documents/{docId}/chunks` | Delete by ids or all |

Chunk fields: `content`, `keywords[]`, `questions[]`, `tags[]`, `positions[]`,
`imageBase64`, `available` (boolean).

### 5.6 Resource: Metadata

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/collections/{id}/metadata/summary` | Aggregated key counts |
| POST | `/v1/collections/{id}/metadata/update` | Bulk update/delete by selector |

### 5.7 Retrieval

`POST /v1/retrieve`
Body:
```
{
  "question": "string (required)",
  "collectionIds": ["..."],
  "documentIds": ["..."],
  "topK": 10,
  "similarityThreshold": 0.2,
  "vectorWeight": 0.7,
  "rerankerId": "...",
  "keyword": "...",
  "highlight": true,
  "crossLanguages": ["en","fr"],
  "metadataCondition": {...},
  "useKnowledgeGraph": false,
  "tocEnhance": false,
  "page": 1,
  "pageSize": 10
}
```
Response: `chunks[]` with `id, content, score, documentId, documentName,
positions, highlights, imageRefs`.

### 5.8 Assistant + Session

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/assistants` | Create |
| GET | `/v1/assistants` | List |
| GET | `/v1/assistants/{id}` | Read |
| PUT | `/v1/assistants/{id}` | Update |
| DELETE | `/v1/assistants` | Delete |
| POST | `/v1/assistants/{id}/sessions` | Create session |
| GET | `/v1/assistants/{id}/sessions` | List sessions |
| POST | `/v1/assistants/{id}/sessions/{sid}/messages` | Send user message (SSE stream response) |

### 5.9 OpenAI-Compatible Endpoints

- `POST /v1/assistants/{id}/openai/chat/completions`
- `POST /v1/agents/{id}/openai/chat/completions`

Request/response conform to the public OpenAI chat-completions wire format,
including `stream` and `tool_calls`. An `extra_body.references` flag adds
citation payloads alongside standard deltas.

### 5.10 Agents

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/agents` | Create from definition JSON |
| GET | `/v1/agents` | List |
| GET | `/v1/agents/{id}` | Read |
| PUT | `/v1/agents/{id}` | Update |
| DELETE | `/v1/agents` | Delete |
| POST | `/v1/agents/{id}/runs` | Start a run (sync or streaming) |
| GET | `/v1/agents/{id}/runs/{rid}` | Inspect run |
| POST | `/v1/agents/{id}/runs/{rid}/cancel` | Cancel run |
| POST | `/v1/agents/{id}/webhooks/{hook}` | Webhook trigger |
| POST | `/v1/agents/{id}/publish` | Publish |
| POST | `/v1/agents/{id}/export` | Export JSON |
| POST | `/v1/agents/import` | Import JSON |

### 5.11 Memory

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/memory` | List memories (scope by agent/user) |
| POST | `/v1/memory` | Write memory |
| DELETE | `/v1/memory/{id}` | Delete |
| GET | `/v1/memory/logs` | Extraction logs |

### 5.12 Providers

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/providers` | List |
| POST | `/v1/providers` | Register |
| PUT | `/v1/providers/{id}` | Update |
| DELETE | `/v1/providers/{id}` | Remove |
| POST | `/v1/providers/{id}/ping` | Validate credentials |

### 5.13 Users, Teams, Tenants, API Keys

Standard CRUD under `/v1/users`, `/v1/teams`, `/v1/tenants`, `/v1/api-keys`.

### 5.14 MCP

- `GET /v1/mcp/tools` — list tools the platform exposes (server mode).
- `POST /v1/mcp/servers` — register an external MCP server (client mode).

### 5.15 Status Codes
`200` OK · `201` Created · `204` No Content · `400` Validation · `401` Auth ·
`403` Forbidden · `404` Not found · `409` Conflict · `413` Payload too large ·
`422` Unprocessable · `429` Rate limited · `500` Server · `503` Downstream
(LLM/engine) unavailable.

### 5.16 Rate Limits
Per API key: default 60 req/min general, 10 concurrent streams, 1 upload
request in flight per collection. Overridable by admin.

### 5.17 Idempotency
`PUT` on a resource by id is idempotent. `POST` creation endpoints accept an
optional `Idempotency-Key` header to dedupe within a 24-hour window.

---

## 6. Data Model (Logical)

Entities and attributes (names are spec-local).

### 6.1 Tenant
`id, name, createdAt, plan, settings{registrationOpen, defaultProviderId, …}`

### 6.2 User
`id, email, displayName, avatar, passwordHash, status, locale, createdAt,
lastLoginAt, tenants[{tenantId, role}]`
States: ACTIVE, INVITED, DISABLED.

### 6.3 Team
`id, tenantId, name, members[{userId, role}]`
Roles: OWNER, ADMIN, MEMBER, VIEWER.

### 6.4 ApiKey
`id, tenantId, ownerUserId, hashedSecret, scopes, createdAt, expiresAt,
lastUsedAt, status`.

### 6.5 Provider
`id, tenantId, kind (llm|embed|rerank|tts|asr|vision), vendor, baseUrl,
credentialRef, models[], capabilities, defaultFor[]`.

### 6.6 Collection (a.k.a. Knowledge Collection)
`id, tenantId, name, description, avatar, embeddingModel, chunkTemplate,
pipelineId, permission, defaults, stats{docs, chunks, tokens},
createdAt, updatedAt, status`.

### 6.7 Document
`id, collectionId, name, mime, sizeBytes, contentHash, source (upload|connector),
connectorRef, metadata{}, status, parseProgress, version, createdAt, updatedAt,
error`.
States: PENDING → PARSING → EMBEDDING → INDEXING → READY · FAILED · CANCELLED.

### 6.8 Chunk
`id, documentId, collectionId, ordinal, parentChunkId, content, tokens,
positions[{page, bbox|lineRange}], keywords[], questions[], tags[],
imageRefs[], enabled, embeddingVersion, createdAt, updatedAt`.

### 6.9 EmbeddingRecord (logical)
`chunkId, modelId, vectorRef, sparseVectorRef, checksum`.

### 6.10 GraphNode / GraphEdge
`id, collectionId, label, type, attributes, sourceChunkIds[]`
`id, fromNodeId, toNodeId, label, weight, sourceChunkIds[]`.

### 6.11 SummaryTreeNode
`id, collectionId, level, summary, childIds[], sourceChunkIds[]`.

### 6.12 Assistant
`id, tenantId, name, avatar, collectionIds[], llmProviderId, llmParams,
systemPrompt, retrievalParams, fallbackText, features{citations,
followUps, tts, voice}, createdAt`.

### 6.13 Session
`id, ownerKind (assistant|agent), ownerId, userId, messages[], variables,
createdAt, lastMessageAt`.

### 6.14 Message
`id, sessionId, role (user|assistant|tool|system), content, references[],
toolCalls[], tokens, createdAt`.

### 6.15 Agent
`id, tenantId, name, graph, templatesUsed, version, publishedUrl,
webhooks[], sharedWith[]`.

### 6.16 AgentRun
`id, agentId, sessionId, triggeredBy (user|webhook|schedule|api), input,
output, events[], status, startedAt, finishedAt, costTokens`.

### 6.17 Memory
`id, scope{agentId, userId|sessionId}, key, content, embedding, sourceRunId,
createdAt, expiresAt`.

### 6.18 Connector
`id, tenantId, kind, credentialRef, targetCollectionId, schedule,
lastRunAt, lastStatus, cursor`.

### 6.19 Pipeline
`id, tenantId, name, stages[], bindings[]`.

### 6.20 AuditEvent
`id, tenantId, actor, action, target, metadata, at`.

Relationships: Tenant 1—N Users, Collections, Agents, Assistants, Providers,
Connectors. Collection 1—N Documents 1—N Chunks. Session 1—N Messages. Agent
1—N AgentRuns. All parent-child deletes cascade logically.

---

## 7. Ingestion & Processing Pipelines

Stages (black-box):

1. **Source** — fetch bytes from upload or connector. *Output:* blob + file
   metadata. *Guarantee:* exactly-once content hash; duplicates collapsed.
2. **Extract** — format-specific conversion to typed blocks. *Guarantee:*
   preserves original order and page/line positions.
3. **Chunker** — template-specific partitioning. *Guarantee:* total
   recoverable content equals extracted content minus explicit skips.
4. **Enricher** — optional TOC, auto-tags, metadata, parent links.
5. **Embedder** — dense vectors; optional sparse (keyword) vectors. *Guarantee:*
   each chunk has exactly one active embedding per model version.
6. **Indexer** — writes to the search engine with tenant/collection partition
   keys.

**Embedding provider selection:** collection setting wins; assistant-level
overrides allowed only when compatible (same vector dim and metric).

**Indexing surface:** a document's chunks become searchable within <10s of
the INDEXING → READY transition under default load.

**Re-ingestion triggers:** embedding-model change, chunk template change,
chunk edit, document update.

---

## 8. Retrieval & Generation

### 8.1 Query Flow
User input → (optional) query rewrite using session history → retrieval
(dense ∥ sparse) → fusion → (optional) rerank → (optional) KG expansion →
(optional) TOC expansion → context packing → LLM call → streamed answer →
citation mapping → final event with usage and references.

### 8.2 Retrieval Capabilities
- **Dense:** single-vector similarity over chunk vectors.
- **Sparse:** token-weighted keyword scoring, with auto and user keywords.
- **Hybrid:** linearly fused score with user-settable weight.
- **Rerank:** cross-encoder scoring of the top-N candidates.
- **Graph-augmented:** entities in the query expand to neighboring chunks.
- **Summary-tree-augmented:** high-level summaries matched first, drill down
  to leaves.
- **Metadata-filtered:** pre-filter by document metadata condition.
- **Cross-language:** query translation fan-out when enabled.

### 8.3 Citation & Grounding
Every LLM-visible reference carries a stable id. Assistant output uses inline
markers like `[1]`, `[2]`. The response envelope includes the full reference
objects, each with collection id, document id, chunk id, snippet, and
positions, so clients can build a "click citation → open source" UX.

### 8.4 Response Modes
- **Streaming** — Server-Sent Events: `message.delta`, `tool.call`,
  `reference`, `error`, `usage`, `done`.
- **Batch** — single JSON response once the answer is complete.
- **OpenAI-compatible stream** — standard delta chunks, with an opt-in extra
  field carrying references.

### 8.5 Deep-Research Mode
Enables an agentic loop up to N iterations: plan, retrieve, read, refine.
Intermediate reasoning is exposed as a separate content channel.

---

## 9. Agent & Workflow Capabilities

### 9.1 Agent Definition
A JSON document with:
- `nodes[]` — id, type, label, config, inputs schema, outputs schema.
- `edges[]` — fromNodeId.port → toNodeId.port.
- `variables` — typed globals.
- `metadata` — name, description, avatar, entry node.

### 9.2 Primitives
- **Control flow:** sequence, branch (Switch), loop (Iteration), parallel (via
  fan-out/aggregator), early exit (End).
- **State:** variables, aggregator nodes, memory reads/writes.
- **I/O:** Start (user input or webhook payload), Message, End, User Feedback.
- **Compute:** Generate (LLM), Retrieval, Code (sandbox), Keyword, Chart,
  External Search, Tool Invocation (HTTP, MCP, SQL, built-in).

### 9.3 Execution Semantics
- **Sync run:** one request, one response.
- **Streaming run:** SSE with per-node events `node.start`, `node.output`,
  `node.error`, plus top-level `message.delta`, `tool.call`, `reference`,
  `done`.
- **Async run:** create run, poll.
- **Webhook trigger:** external POST starts a run; body becomes `Start` input.

### 9.4 Determinism & Retries
Nodes declare retry policy (max retries, backoff). Non-deterministic nodes
(LLM, tools) cache by a user-supplied idempotency key.

### 9.5 Publishing
Publishing an agent freezes a version and exposes:
- A public chat URL.
- An embeddable iframe snippet.
- An OpenAI-compatible endpoint.
- A webhook URL per declared trigger.

---

## 10. Integration Matrix

### 10.1 LLM Providers (supported options, not mandated)
OpenAI, Anthropic, Google (Gemini / Vertex), Azure OpenAI, AWS Bedrock,
DeepSeek, Mistral, MiniMax, Alibaba Tongyi/Qwen, Moonshot Kimi, Zhipu GLM,
Baichuan, Yi, Stepfun, xAI Grok, Perplexity, Groq, Together, Fireworks,
OpenRouter, SiliconFlow, Ollama, Xinference, LocalAI, LM Studio, Nvidia API,
VolcanoArk, Tencent Hunyuan, Baidu, Gitee AI, ModelScope, Novita, PPIO, PerfX,
Upstage, 01.AI, Jiekou, XunFei Spark, plus any OpenAI-compatible endpoint.

### 10.2 Embedding Providers
OpenAI, Voyage, Cohere, Jina, BGE, BCE, Perplexity, Google, Tongyi, Ollama,
Xinference, LocalAI, plus OpenAI-compatible.

### 10.3 Reranker Providers
Jina, Cohere, BGE, Tongyi, Voyage, Xinference, Huggingface, plus
OpenAI-compatible.

### 10.4 Vector / Search Engines
Elasticsearch, OpenSearch, Infinity (embedded).

### 10.5 Relational Stores
MySQL, PostgreSQL, OceanBase.

### 10.6 Object Stores
MinIO, AWS S3 (and S3-compatible), Azure Blob, Aliyun OSS, Google Cloud
Storage.

### 10.7 Cache
Redis, Valkey.

### 10.8 Document Source Connectors
Local upload, S3-compatible, AWS S3, Google Drive, Google Cloud Storage,
Dropbox, Notion, Confluence, Discord, Gmail, IMAP, WebDAV, Airtable, GitHub,
GitLab, Bitbucket, JIRA, Asana, Zendesk, Seafile, RSS, DingTalk AI Table.

### 10.9 Auth
Local password; SSO via OIDC / SAML (configurable); personal API keys.

### 10.10 Voice
ASR: Tencent Cloud, provider-specific via Provider API.
TTS: OpenTTS, SparkTTS, FishAudio, Tongyi Qwen TTS, provider-specific.

### 10.11 MCP
Bidirectional: server-side exposure and client-side consumption.

---

## 11. Configuration Surface

Configuration is split across: environment variables (deployment), config file
(service-level), per-tenant settings, and per-user preferences.

### 11.1 Deployment (env / file)
| Name | Type | Default | Notes |
|---|---|---|---|
| `HTTP_PORT` | int | 9380 | API + UI port |
| `DB_KIND` | enum(mysql, postgres, oceanbase) | mysql | Relational DB |
| `DB_URL` | string | — | DSN |
| `SEARCH_KIND` | enum(elasticsearch, opensearch, infinity) | elasticsearch | |
| `SEARCH_URL` | string | — | |
| `OBJECT_STORE_KIND` | enum(minio, s3, azure, oss, gcs) | minio | |
| `OBJECT_STORE_URL` | string | — | |
| `CACHE_KIND` | enum(redis, valkey) | redis | |
| `CACHE_URL` | string | — | |
| `JWT_SECRET` | string | — | Required |
| `ENCRYPTION_KEY` | string | — | At-rest secret envelope |
| `SANDBOX_KIND` | enum(local, gvisor, remote) | gvisor | Code executor |
| `MAX_UPLOAD_MB` | int | 128 | Per file |
| `WORKER_COUNT` | int | auto | Parsing workers |
| `GPU_ENABLED` | bool | false | For deep-layout parser |
| `LOG_LEVEL` | enum | info | |
| `REGISTRATION_OPEN` | bool | true | Initial default |
| `TELEMETRY_ENABLED` | bool | false | Opt-in only |

### 11.2 Tenant Settings (UI / API)
Default LLM, default embedding, default reranker, registration policy, team
quotas, concurrency caps, allowed providers, webhook allowlist, data
retention windows.

### 11.3 Collection Settings
Name, description, avatar, embedding model, chunk template, pipeline, default
retrieval params, permission, auto-tag vocabulary, metadata schema.

### 11.4 Assistant Settings
All fields in 6.12.

### 11.5 User Preferences
Locale, theme, default LLM, TTS voice, notification preferences.

Change semantics: deployment vars require restart; tenant/collection/assistant
settings take effect on next request; embedding-model changes are destructive
and require confirmation.

---

## 12. Non-Functional Requirements

### 12.1 Performance Targets (single node, default hardware)
- Retrieval p50 ≤ 150 ms, p95 ≤ 500 ms for `topK=10` over ≤1M chunks.
- First-token latency p50 ≤ 1.5 s (excluding LLM provider tail).
- Parsing throughput ≥ 10 pages/s/worker for PDFs without heavy layout.
- UI page load p50 ≤ 2 s on a 10 Mbps link.

### 12.2 Throughput
- ≥ 60 chat turns/minute per node at default concurrency.
- ≥ 100 concurrent streams per cluster at recommended size.

### 12.3 Concurrency
Stateless API nodes, horizontally scalable. Parsing workers are a pool; at
least one worker per node. Cluster coordinates through the cache and the
relational DB.

### 12.4 Resource Footprint (minimum)
CPU ≥ 4 cores, RAM ≥ 16 GB, Disk ≥ 50 GB, optional GPU for deep-layout
parsing and local models. Recommended for production: 8+ cores, 32+ GB RAM,
separate hosts for search engine and object store.

### 12.5 Scalability
Single-node supported. Horizontal scale via stateless API plus scale-out
workers. The search engine and object store scale per their own topology.

### 12.6 Observability
- **Logs:** structured JSON, per-request correlation id.
- **Metrics:** Prometheus-compatible at `/metrics` — request rate, latency
  histograms, queue depth, tokens in/out per provider, parse success rate.
- **Traces:** OpenTelemetry-compatible export when configured.

### 12.7 Security
- TLS termination at the edge; internal TLS optional.
- Secrets encrypted at rest using the deployment encryption key.
- Authentication: local password + optional SSO.
- Authorization: tenant isolation at every query; team roles for resource
  access.
- Data isolation: every query carries a tenant partition key; cross-tenant
  access is impossible by construction.
- Audit trail for privileged admin actions.
- Sandbox for user-authored code.

---

## 13. Deployment Topology

### 13.1 Roles (describe by function, not vendor)
- **API service** — stateless HTTP server; UI assets; REST + OpenAI-compat +
  MCP.
- **Worker service** — parsing, chunking, embedding, indexing.
- **Relational DB** — metadata, users, tenants, audit.
- **Search engine** — vector + sparse index.
- **Object store** — original files, large derived artifacts.
- **Cache** — sessions, queues, coordination.
- **Sandbox runner** — isolated execution for user code.
- **Optional: Voice providers, LLM providers, Connector runners.**

### 13.2 Communication
API ↔ DB, cache, search, object store (synchronous). API → worker queue via
cache. Worker ↔ search engine, object store, embedding/LLM providers.

### 13.3 Deployment Modes
- **Single-node** — all roles on one host via Compose.
- **Cluster** — API and worker services scaled horizontally behind a load
  balancer; shared DB, cache, search, object store.
- **Kubernetes** — one Helm chart with role-specific deployments.

### 13.4 Hardware (minimums)
CPU ≥ 4, RAM ≥ 16 GB, Disk ≥ 50 GB. GPU optional.

---

## 14. UI / UX Specification

Tone: **professional, data-dense, pragmatic**. Dark and light themes. High
information density; keyboard-accessible; screen-reader labels on all
interactive controls; color contrast AA or better; RTL support.

### 14.1 Screens

**S1. Login / Register** — email + password; SSO buttons when configured;
"forgot password" flow.

**S2. Home / Overview** — cards for Knowledge, Chat, Search, Agents, with
recent activity and quickstart links.

**S3. Knowledge List** — table of collections with counts, last activity,
owner, actions (create, rename, delete, open).

**S4. Collection Detail** — tabs: Documents, Configuration, Retrieval Test,
Knowledge Graph, Metadata.

**S5. Document List** — grid/table; per-row status, size, type, parse
actions (start, stop, re-parse), metadata edit, delete.

**S6. Document Parse View** — split: left pane shows original (PDF/HTML/
image rendered page by page), right pane shows chunk list with highlights
and edit controls.

**S7. Retrieval Test** — query input, parameter sliders (topK, threshold,
weight, rerank toggle, cross-lang toggle, metadata filter builder),
ranked chunk list with scores and snippets.

**S8. Chat** — assistant picker, conversation pane with streamed output,
citation chips that open a side drawer with source. Voice-in mic button;
TTS play button per message; thinking-mode toggle; model-comparison mode
showing up to three answers side-by-side.

**S9. Assistant Config** — all fields in 6.12, with live preview.

**S10. Agent List** — grid of agents with status and last-run chip.

**S11. Agent Builder** — canvas with draggable node palette, connections,
per-node inspector, variable panel, test run panel, version history.

**S12. Agent Run View** — step-by-step timeline with inputs/outputs per
node and errors.

**S13. Search** — single input; ranked passages; optional generated
summary; collection selector.

**S14. Admin Dashboard** — users, teams, tenants, providers, services
health, queue depth, usage.

**S15. Profile / API Keys / Preferences** — account, password, locale,
theme, TTS voice, API key list with create/revoke.

**S16. Provider Management** — register/edit LLM/embed/rerank/TTS/ASR
providers; test connectivity.

**S17. Connector Management** — register source connectors; schedule, last
run, status.

**S18. Memory Viewer** — browse agent/user memories and extraction logs.

### 14.2 Common Patterns
- Global search bar (⌘K / Ctrl+K).
- Toast notifications for long-running actions.
- Progress bars attached to document rows.
- Confirmation modals for destructive actions.

### 14.3 Accessibility
WCAG 2.1 AA target. All actions reachable by keyboard. Focus-visible
outlines. Live regions announce stream progress.

---

## 15. Acceptance Test Suite

End-to-end scenarios. All must pass for functional equivalence.

**AT-01 Happy Path Chat.** Precondition: empty tenant. Steps: sign up, create
collection, upload a PDF, parse, create assistant bound to the collection,
ask a question whose answer is on page 3. Expected: streamed answer
containing a citation whose chunk resolves to page 3 of that PDF.

**AT-02 Parse All Formats.** Upload one file of each supported format; all
transition to READY or UNSUPPORTED with a clear reason.

**AT-03 Metadata Filtering.** Attach metadata `owner=legal` to 3 of 10 docs;
query with filter; only chunks from those 3 docs are returned.

**AT-04 Cross-Language.** Mix English and Chinese documents; query in English
returns Chinese hits and vice versa when cross-language is on.

**AT-05 Citation Integrity.** Every `[n]` in an answer has a matching entry
in the response `references[]` and links to a real chunk.

**AT-06 OpenAI Client Compatibility.** Point an OpenAI SDK at the
compatibility endpoint; chat and streaming both work with no code changes
beyond base URL and key.

**AT-07 Tenant Isolation.** User A in Tenant 1 cannot read or enumerate any
resource of Tenant 2 via UI or API.

**AT-08 Agent Run with Tool Call.** Build agent: Start → Generate with Tool
list {weather HTTP} → End. Run returns tool output in a structured final
message.

**AT-09 Agent Publish + Webhook.** Publish agent; POST to webhook URL;
observe run with webhook payload as input.

**AT-10 Structured Output.** Assistant with declared JSON schema returns
output that validates; malformed output is re-attempted once.

**AT-11 Sandbox Isolation.** Code node attempting filesystem escape or
network outside allowlist fails with a sandbox error, not a host compromise.

**AT-12 KG Build + Browse.** Rebuild KG on a 50-doc collection; UI displays
nodes and edges; query uses KG expansion.

**AT-13 Summary-Tree Retrieval.** Build tree on 500-doc collection; a
"summarize everything about X" query returns a coherent synthesis covering
>1 document.

**AT-14 Admin Close Registration.** After admin toggles registration off,
sign-up endpoint returns 403.

**AT-15 Connector Sync.** Register Google Drive connector; new file appears
in collection within one sync cycle; deleted file is marked deleted.

**AT-16 Voice + TTS.** Record audio question; assistant answers; click
play-TTS and hear the answer.

**AT-17 Dark Mode + RTL.** Switch theme and locale to Arabic; layout
mirrors; all labels are translated.

**AT-18 Horizontal Scale.** Scale API replicas from 1 to 3; sessions remain
stable; retrievals stay within p95 target.

**AT-19 Observability.** `/metrics` exposes required counters; a trace for
a single chat turn shows retrieval → LLM call spans.

**AT-20 Backup/Restore.** Snapshot DB + object store + search; restore on a
new host; all assistants, collections, chunks, and citations still resolve.

---

## 16. Explicit Non-Goals

- **Training or fine-tuning models.** The product consumes models; it does
  not train them.
- **Acting as a vector database.** The platform uses a vector engine but
  does not expose itself as a general-purpose vector DB to other apps.
- **Generic workflow/BPM engine.** Workflows are AI-oriented; no
  human-approval trees, no SLAs, no SAP-style forms.
- **Billing / subscription management for tenants.** Out of scope.
- **Mobile native apps.** Responsive web only.
- **Real-time collaborative editing of chunks/agents.** Last-writer-wins is
  acceptable.
- **Air-gapped enterprise PKI integrations.** Standard TLS + API keys + SSO
  only.
- **Model routing optimizer / cost optimizer across providers.** Users pick
  providers explicitly.
- **Built-in analytics dashboards for end-user business data.** Charts
  exist inside agent runs, not as a general BI tool.
- **Document editing.** Source documents are read-only inside the
  platform.

---

## 17. Open Questions

1. **Chunk-edit history semantics.** Are chunk edits versioned or destructive?
   Required for compliance-sensitive deployments.
2. **Retention policy on agent runs and traces.** Default TTL? Per-tenant
   override? GDPR delete-by-user semantics?
3. **Exact fusion formula weights.** Is the vector/keyword weight linear,
   or do we need a learned fuser per collection?
4. **Reranker selection cost/benefit thresholds.** When should the UI
   recommend enabling the reranker automatically?
5. **Cross-collection retrieval.** An assistant can bind multiple
   collections — how are top-K slots split across them (round-robin, by
   score, by user weight)?
6. **Embedding model migration UX.** Online re-index vs. shadow collection?
7. **Memory conflict resolution.** Two memories with overlapping facts —
   newest wins, or LLM-mediated merge?
8. **Webhook security model.** Signed secrets per hook? Allowlist by IP?
   Replay protection window?
9. **Sandbox language surface.** Which stdlib/third-party packages are in
   scope by default for Python and JS nodes?
10. **Publishing model for apps.** Is there a review workflow, or are all
    published agents immediately public?
11. **Connector incrementality.** Per-connector declared guarantees (append-
    only vs. full-sync) — is a common contract feasible or connector-specific?
12. **Quota and rate-limit UX.** Where are 429s surfaced — per-user, per-
    tenant, per-API-key?
13. **OpenAI-compat coverage.** Do we implement `/v1/models`, `/v1/embeddings`,
    `/v1/images`? Or only `/chat/completions`?
14. **Citation stability across re-parses.** If a document is re-parsed,
    do prior answers' citations still resolve to the same chunks?
15. **Internationalization of citations.** If the query is translated for
    cross-language retrieval, which language is the final answer in?

---

*End of SPEC.md*
