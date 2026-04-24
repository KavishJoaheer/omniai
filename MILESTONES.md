# Omni-AI Milestone Plan

This plan is optimized for the fastest path from the current scaffold to the
full product described in `SPEC.md`, `SPEC_SUMMARY.md`, and `ARCHITECTURE.md`.

Legend:
- `Now` means already started in code
- `Manual input needed` means I will pause and ask you when that item blocks progress

## M1. Platform Core and Persistence

Status: `Now`

Goal:
- Replace the in-memory backend with a real persistence foundation we can build on

Deliverables:
- SQLAlchemy-backed relational schema
- Bootstrap tenant model
- Persistent collections and documents
- Configurable `DB_URL`
- Local dev database setup
- Safer backend dependency wiring

Exit criteria:
- Collections and documents survive server restarts
- Backend runs without the in-memory store
- CRUD foundation is stable enough for the next layers

Manual input needed:
- None for the first pass

## M2. Auth, Tenancy, and Admin Foundation

Goal:
- Add the security and multi-tenant backbone early so later work does not need rewrites

Deliverables:
- User model
- Local login flow
- Session auth and API key auth
- Tenant/team/role models
- Basic admin APIs
- Audit event model

Exit criteria:
- Authenticated users can only see tenant-scoped resources
- API keys work for machine access

Manual input needed:
- Registration policy preference
- Initial admin user details if you want seeded accounts

## M3. Knowledge Ingestion Core

Goal:
- Make document upload and processing real

Deliverables:
- Multipart upload handling
- Object storage integration
- Document status lifecycle
- Worker process and job queue
- Parse pipeline skeleton
- Initial parser set: PDF, DOCX, TXT, MD, CSV, HTML

Exit criteria:
- Uploaded files move from `PENDING` to `READY` or `FAILED`
- Stored file bytes can be retrieved and traced to records

Manual input needed:
- If you want a specific object store target instead of local/dev defaults

## M4. Chunking, Embeddings, and Retrieval

Goal:
- Turn uploaded documents into searchable grounded context

Deliverables:
- Chunking templates
- Chunk storage and review model
- Embedding provider abstraction
- Initial embedding adapters
- Search index integration
- Dense + sparse + hybrid retrieval
- Retrieval test API

Exit criteria:
- A query returns ranked chunks with scores and snippets
- Re-indexing works after document or chunk changes

Manual input needed:
- Provider credentials if you want hosted embeddings instead of local/dev mode

## M5. Assistant Chat and Citations

Goal:
- Deliver the core RAG product loop

Deliverables:
- Assistant model
- Chat sessions and messages
- SSE streaming
- Citation mapping
- Fallback responses
- OpenAI-compatible chat endpoint

Exit criteria:
- AT-01, AT-05, and AT-06 are passing or close to passing

Manual input needed:
- Preferred first LLM providers and credentials

## M6. Frontend Integration for Knowledge and Chat

Goal:
- Replace UI placeholders with real workflows

Deliverables:
- API client layer
- Collection/document screens wired to backend
- Upload flow and parse progress
- Retrieval test screen
- Assistant creation flow
- Real chat UI with citation drawer

Exit criteria:
- A user can create a collection, add documents, and chat from the browser

Manual input needed:
- Branding/content decisions only if you want custom polish early

## M7. Agent Runtime and Builder

Goal:
- Deliver the second major pillar of the product

Deliverables:
- Agent data model
- Graph execution runtime
- Initial node types: Start, End, Retrieval, Generate, Message
- Async runs and run history
- Agent builder canvas foundation
- Publish and session support

Exit criteria:
- A basic multi-step agent can execute end-to-end

Manual input needed:
- None for the initial runtime

## M8. Advanced Agent Nodes and Sandbox

Goal:
- Make agents genuinely useful, not just graph demos

Deliverables:
- Code Executor node
- Tool Invocation node
- Structured output
- Webhook trigger flow
- Chart generation node
- Sandboxed execution boundary

Exit criteria:
- AT-08, AT-09, and AT-10 are passing or close to passing

Manual input needed:
- Any external tools or allowlists you want enabled

## M9. Advanced Retrieval and Knowledge Features

Goal:
- Build the higher-cost capabilities from the spec

Deliverables:
- Metadata-filtered retrieval
- Cross-language retrieval
- TOC expansion
- Parent-child chunking
- Knowledge graph indexing and browse API
- Hierarchical summarization index

Exit criteria:
- AT-03, AT-04, AT-12, and AT-13 are passing or close to passing

Manual input needed:
- Language priorities if you want optimization for specific locales first

## M10. Connectors, MCP, and Voice

Goal:
- Expand the platform beyond direct uploads

Deliverables:
- Connector interface plus reference connector
- MCP server mode
- MCP client mode
- Voice input and TTS abstraction
- Initial local/dev ASR and TTS adapters

Exit criteria:
- External sync and tool exposure are working in the reference path

Manual input needed:
- Connector accounts and any third-party credentials

## M11. Hardening, Deployment, and Acceptance Gate

Goal:
- Make the project shippable

Deliverables:
- Automated tests mapped to AT-01 through AT-20
- Metrics and tracing expansion
- Docker Compose completion
- Helm/Kubernetes packaging
- Backup and restore path
- Performance and stability pass
- Documentation pass

Exit criteria:
- Acceptance suite passes
- Local deployment and target deployment are both documented and repeatable

Manual input needed:
- Final deployment target
- Infrastructure credentials if deploying to managed services

## Build Order Notes

- The fastest critical path is `M1 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9 -> M10 -> M11`
- `M2` starts early in parallel because tenancy and auth affect almost everything
- I will keep asking you only when a manual step becomes a real blocker

