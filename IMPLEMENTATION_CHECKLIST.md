# Omni-AI Implementation Checklist

Current repo status snapshot based on the code present in this folder.

Legend:
- `[x]` Implemented in code
- `[~]` Partially implemented or scaffolded only
- `[ ]` Not implemented yet

## Foundation

- [x] Root monorepo structure
- [x] Root `README.md`
- [x] Root `Makefile`
- [x] Root `.env.example`
- [x] Basic `.gitignore`
- [x] Backend package scaffold under `backend/`
- [x] Frontend package scaffold under `frontend/`
- [x] Local Docker Compose starter under `deploy/compose/docker-compose.yml`
- [ ] CI workflow
- [ ] Git repository initialization

## Backend API

- [x] FastAPI app factory
- [x] Typed settings with `pydantic-settings`
- [x] CORS configuration
- [x] Simple request-count middleware
- [x] Common response envelope shape `{code, message, data}`
- [x] `/v1/health` endpoint
- [x] `/v1/metrics` endpoint
- [x] `/v1/collections` list endpoint
- [x] `/v1/collections` create endpoint
- [x] `/v1/collections/{collection_id}` get endpoint
- [x] `/v1/collections/{collection_id}/documents` list endpoint
- [x] `/v1/collections/{collection_id}/documents` create endpoint
- [x] Auth register endpoint
- [x] Auth login endpoint
- [x] Auth logout endpoint
- [x] Current-user endpoint
- [x] API key list/create/revoke endpoints
- [x] Tenant info endpoints
- [x] Team list/create endpoints
- [x] Basic admin endpoints
- [ ] Chunk endpoints
- [ ] Retrieval endpoints
- [ ] Assistant endpoints
- [ ] Session endpoints
- [ ] Agent endpoints
- [ ] Provider endpoints
- [ ] API key endpoints
- [ ] OpenAI-compatible endpoints
- [ ] MCP endpoints

## Backend Architecture

- [x] Basic package split for `config`, `domain`, `application`, `interfaces`, and `observability`
- [x] Domain models for `Collection` and `Document`
- [x] Application service for collection and document operations
- [x] SQLAlchemy persistence foundation
- [~] Architecture-aligned folder naming
  Note: the naming follows the architecture doc, but most planned modules are still empty or absent.
- [ ] Repository abstractions / ports
- [ ] Real persistence adapters
- [ ] Worker process
- [ ] Scheduler process
- [ ] Sandbox runner
- [ ] Dependency injection container

## Data and Persistence

- [ ] PostgreSQL integration
- [x] SQLAlchemy models
- [ ] Alembic migrations
- [ ] OpenSearch integration
- [ ] MinIO / object store integration
- [ ] Redis / queue integration
- [ ] Persistent document storage
- [ ] Persistent collection storage
- [x] Persistent document metadata storage
- [x] Persistent collection metadata storage
- [x] Tenant-aware relational partitioning

## Knowledge and Ingestion

- [ ] Multipart file upload handling
- [ ] Actual file byte storage
- [ ] MIME validation
- [ ] Parsing pipeline
- [ ] Multi-format extraction
- [ ] Chunking templates
- [ ] Chunk review and edit
- [ ] Embedding model selection
- [ ] Embedding generation
- [ ] Indexing
- [ ] Re-parse workflow
- [ ] Retrieval test panel backend logic

## Retrieval and Chat

- [ ] Dense retrieval
- [ ] Sparse retrieval
- [ ] Hybrid fusion
- [ ] Reranking
- [ ] Metadata-filtered retrieval
- [ ] Cross-language retrieval
- [ ] TOC expansion
- [ ] Knowledge graph expansion
- [ ] Citation mapping
- [ ] SSE streaming chat
- [ ] Assistant configuration and persistence
- [ ] Conversation memory
- [ ] Deep research mode

## Agents and Workflows

- [~] Agent section exists in frontend navigation
- [ ] Agent data model
- [ ] Agent builder canvas
- [ ] Node library
- [ ] Agent runtime
- [ ] Agent sessions
- [ ] Agent memory
- [ ] Structured output
- [ ] Sandbox code execution
- [ ] Chart generation
- [ ] Publish / share flow
- [ ] Webhook triggers

## Auth, Tenancy, and Security

- [x] User signup / login
- [x] Session auth
- [x] API key auth
- [x] Tenant model
- [x] Team model
- [x] Roles and permissions foundation
- [x] Audit trail model and endpoints
- [ ] Secret encryption
- [ ] Rate limiting
- [ ] Idempotency keys
- [ ] Webhook signature validation

## Frontend

- [x] React + TypeScript + Vite app
- [x] App shell with sidebar navigation
- [x] Overview page
- [x] Knowledge page shell
- [x] Chat page shell
- [x] Agents page shell
- [x] Search page shell
- [x] Admin page shell
- [x] Custom base styling
- [x] Responsive layout
- [ ] Real API integration
- [ ] Data fetching layer
- [ ] Forms for create/edit flows
- [ ] Authentication UI
- [ ] Document upload UI
- [ ] Parse progress UI
- [ ] Retrieval testing UI
- [ ] Citation drawer with live data
- [ ] Agent canvas UI
- [ ] Provider management UI
- [ ] Profile / API keys UI
- [ ] i18n / RTL support
- [ ] Dark mode toggle

## Dev Experience and Operations

- [x] Backend local run instructions
- [x] Frontend local run instructions
- [x] Frontend production build works
- [x] Backend smoke-check completed manually during setup
- [~] Docker Compose local dev
  Note: only `api` and `frontend` services are wired right now, not the full platform stack from the architecture doc.
- [ ] Automated backend tests
- [ ] Automated frontend tests
- [ ] End-to-end tests
- [ ] Linting
- [ ] Formatting automation
- [ ] Kubernetes / Helm deployment
- [ ] Production-ready Compose stack

## Overall Product Status

- [~] Spec-aligned starter foundation
- [ ] MVP product from `SPEC.md`
- [ ] Standard-tier features from `SPEC.md`
- [ ] Extended-tier features from `SPEC.md`
