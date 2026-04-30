"""Generate the Omni-AI industry-grade audit PDF report.

Run from repo root:
    python generate_report.py

Output: ./omniai_industry_grade_report.pdf
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ─── Colors / styles ────────────────────────────────────────────────────────

BRAND = colors.HexColor("#1F3A8A")     # deep blue
ACCENT = colors.HexColor("#0E7C7B")    # teal
DONE = colors.HexColor("#0E7C42")      # green
PARTIAL = colors.HexColor("#B26B00")   # amber
MISSING = colors.HexColor("#A11626")   # red
GREY = colors.HexColor("#4B5563")
LIGHT_GREY = colors.HexColor("#E5E7EB")
BG_GREY = colors.HexColor("#F8FAFC")

styles = getSampleStyleSheet()

H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                    fontSize=22, leading=26, textColor=BRAND, spaceAfter=12)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                    fontSize=16, leading=20, textColor=BRAND, spaceBefore=14, spaceAfter=8)
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold",
                    fontSize=12, leading=16, textColor=ACCENT, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica",
                      fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9, leading=12, textColor=GREY)
COVER_TITLE = ParagraphStyle("CoverTitle", parent=H1, fontSize=32, leading=38,
                             alignment=TA_CENTER, textColor=BRAND, spaceAfter=16)
COVER_SUB = ParagraphStyle("CoverSub", parent=BODY, fontSize=14, leading=20,
                           alignment=TA_CENTER, textColor=GREY, spaceAfter=8)
QUOTE = ParagraphStyle("Quote", parent=BODY, fontSize=10, leading=14,
                       leftIndent=20, rightIndent=20, textColor=GREY,
                       fontName="Helvetica-Oblique", spaceAfter=8)
BULLET = ParagraphStyle("Bullet", parent=BODY, fontSize=10, leading=14,
                        leftIndent=18, bulletIndent=6, spaceAfter=2)
MILESTONE_TITLE = ParagraphStyle("MS", parent=H3, fontSize=13, textColor=BRAND)


# ─── Helper builders ────────────────────────────────────────────────────────


def status_cell(symbol: str, color):
    return Paragraph(
        f'<font color="{color.hexval()}"><b>{symbol}</b></font>',
        ParagraphStyle("sc", parent=BODY, alignment=TA_CENTER, fontSize=11),
    )


DONE_CELL = lambda: status_cell("✓ Done", DONE)        # ✓
PARTIAL_CELL = lambda: status_cell("◐ Partial", PARTIAL)  # ◐
MISSING_CELL = lambda: status_cell("✗ Missing", MISSING)  # ✗


def feature_table(rows: list[tuple[str, str, str]]) -> Table:
    """rows = [(feature, status_label, notes)] where status_label in {done,partial,missing}."""
    table_data = [[
        Paragraph("<b>Feature</b>", BODY),
        Paragraph("<b>Status</b>", BODY),
        Paragraph("<b>Notes</b>", BODY),
    ]]
    for feature, status, notes in rows:
        if status == "done":
            cell = DONE_CELL()
        elif status == "partial":
            cell = PARTIAL_CELL()
        else:
            cell = MISSING_CELL()
        table_data.append([
            Paragraph(feature, BODY),
            cell,
            Paragraph(notes, SMALL),
        ])
    table = Table(table_data, colWidths=[2.0 * inch, 0.9 * inch, 3.5 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_GREY]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GREY),
    ]))
    return table


def metric_card(label: str, value: str, sub: str = "") -> Table:
    cell = [
        [Paragraph(f"<b><font size=22 color='{BRAND.hexval()}'>{value}</font></b>", BODY)],
        [Paragraph(f"<b>{label}</b>", BODY)],
    ]
    if sub:
        cell.append([Paragraph(sub, SMALL)])
    t = Table(cell, colWidths=[1.6 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_GREY),
        ("BOX", (0, 0), (-1, -1), 0.5, ACCENT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawRightString(letter[0] - 0.6 * inch, 0.4 * inch,
                           f"Omni-AI Audit Report | Page {doc.page}")
    canvas.drawString(0.6 * inch, 0.4 * inch,
                      f"Generated {date.today().isoformat()}")
    canvas.restoreState()


# ─── Build the document ────────────────────────────────────────────────────


def build_story() -> list:
    story: list = []

    # ---- COVER ----
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph("Omni-AI", COVER_TITLE))
    story.append(Paragraph("Industry-Grade Readiness Audit",
                           ParagraphStyle("c1", parent=COVER_SUB, fontSize=18, textColor=ACCENT)))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Comparative Analysis vs. RAGFlow",
                           ParagraphStyle("c2", parent=COVER_SUB, fontSize=14)))
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph(f"Report date: <b>{date.today().strftime('%B %d, %Y')}</b>", COVER_SUB))
    story.append(Paragraph("Codebase: monorepo (Python backend + React frontend)", COVER_SUB))
    story.append(Paragraph("Status: <b>v0.1 — Beta</b>", COVER_SUB))
    story.append(PageBreak())

    # ---- TABLE OF CONTENTS ----
    story.append(Paragraph("Contents", H1))
    toc = [
        "1. Executive Summary",
        "2. Codebase Metrics",
        "3. Architecture Overview",
        "4. Feature Inventory",
        "    4.1 Authentication, Authorization & Security",
        "    4.2 Knowledge Base (Collections, Documents, Ingestion)",
        "    4.3 Search & Retrieval Pipeline",
        "    4.4 Chat & Conversational AI",
        "    4.5 Agents & Workflow Engine",
        "    4.6 Connectors (Data Ingestion Sources)",
        "    4.7 Deployments & Public Chat Surface",
        "    4.8 Sandbox / Code Execution",
        "    4.9 Observability & Operations",
        "    4.10 Multi-tenancy & RBAC",
        "    4.11 Frontend (React UI)",
        "5. Recent Improvements (This Iteration)",
        "6. Gap Analysis vs. Industry Grade",
        "7. Milestone Roadmap",
        "8. Conclusion",
    ]
    for line in toc:
        story.append(Paragraph(line, BODY))
    story.append(PageBreak())

    # ---- 1. EXECUTIVE SUMMARY ----
    story.append(Paragraph("1. Executive Summary", H1))
    story.append(Paragraph(
        "Omni-AI is a self-hosted Retrieval-Augmented Generation (RAG) and agent platform "
        "designed to compete with RAGFlow on a feature-by-feature basis. The codebase implements a "
        "clean hexagonal architecture (ports/adapters), supports multi-tenancy, embeddings via "
        "Ollama, hybrid (BM25 + dense) search with Reciprocal Rank Fusion, Maximal Marginal "
        "Relevance diversification, parent-chunk expansion, knowledge-graph augmentation, and "
        "multi-step agent workflows with sandboxed code execution.",
        BODY))
    story.append(Paragraph(
        "<b>Status today:</b> the platform is feature-complete enough for production pilot "
        "deployments inside a single trusted environment. <b>165 backend tests</b> and "
        "<b>7 frontend tests</b> pass on every CI run across Python 3.11 and 3.12. The codebase "
        "is approximately <b>13,100 lines of backend Python</b> and <b>4,000 lines of frontend "
        "TypeScript</b>, organised into 17 HTTP route modules, 13 SQL migrations, and 17 plugin "
        "implementations covering parsers, embeddings, LLMs, rerankers, OCR, sandboxes and chunk "
        "templates.",
        BODY))
    story.append(Paragraph(
        "<b>Where it matches RAGFlow today:</b> hybrid retrieval, 4 chunk templates, Okapi BM25, "
        "RRF fusion, MMR re-ranking, parent-chunk expansion, knowledge-graph extraction and "
        "augmentation, OCR via Tesseract & vision LLMs, document-level RBAC, password reset, "
        "session revocation, structured JSON logs, Prometheus metrics, hot-pluggable LLM "
        "providers (Ollama, OpenAI, Anthropic, Gemini), agent workflows with sandboxed Python, "
        "public deployment slugs.",
        BODY))
    story.append(Paragraph(
        "<b>Where work remains:</b> distributed coordination (single-node assumptions in the "
        "connector scheduler), production Kubernetes manifests, Grafana dashboards, frontend "
        "UI test depth, full WCAG 2.1 accessibility audit, conversation/agent export, advanced "
        "telemetry (per-tenant cost dashboards, retrieval relevance metrics over time).",
        BODY))
    story.append(PageBreak())

    # ---- 2. CODEBASE METRICS ----
    story.append(Paragraph("2. Codebase Metrics", H1))
    story.append(Paragraph(
        "The numbers below reflect the current state of the main branch.", BODY))
    story.append(Spacer(1, 0.2 * inch))

    metrics_table = Table([
        [metric_card("Backend LoC", "13.1K", "Python 3.11+"),
         metric_card("Frontend LoC", "4.0K", "React + TS"),
         metric_card("Backend Tests", "165", "100% passing"),
         metric_card("Frontend Tests", "7", "Vitest + RTL")],
        [metric_card("HTTP Routes", "17", "FastAPI modules"),
         metric_card("Migrations", "13", "Alembic"),
         metric_card("Plugins", "17", "Pluggable adapters"),
         metric_card("Connectors", "3", "Local, S3, Web")],
    ], colWidths=[1.7 * inch] * 4)
    metrics_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Quality gates passing on CI:", H3))
    for item in [
        "Backend: <b>ruff</b> lint clean, <b>pyright</b> type-check clean, <b>pytest</b> 165/165 passing",
        "Frontend: <b>tsc --noEmit</b> clean, <b>vitest</b> 7/7 passing",
        "Coverage: <b>codecov</b> upload (Python 3.12 leg)",
        "Multi-version matrix: Python 3.11 + 3.12 both green",
    ]:
        story.append(Paragraph("• " + item, BULLET))
    story.append(PageBreak())

    # ---- 3. ARCHITECTURE OVERVIEW ----
    story.append(Paragraph("3. Architecture Overview", H1))
    story.append(Paragraph(
        "The platform follows a strict <b>hexagonal (ports & adapters)</b> architecture. The "
        "domain layer (entities, value objects, validation) is pure Python with no I/O. "
        "Application services orchestrate use-cases. Ports define contracts and live in "
        "<i>omniai/ports/</i>. Adapters in <i>omniai/adapters/</i> and <i>omniai/plugins/</i> "
        "implement those contracts against real infrastructure (SQLAlchemy, S3-compatible "
        "object stores, OpenSearch, Ollama, etc.).",
        BODY))

    story.append(Paragraph("Layer responsibilities", H2))
    story.append(Paragraph(
        "<b>Domain</b>: <i>knowledge</i>, <i>agents</i>, <i>connectors</i>, <i>deployments</i> "
        "modules each contain their own Pydantic models and value objects. No SQL, no HTTP, "
        "no third-party SDKs leak into the domain.<br/>"
        "<b>Application</b>: services such as <i>IngestionService</i>, <i>RetrievalService</i>, "
        "<i>ChatService</i>, <i>AgentService</i>, <i>DeploymentService</i>, "
        "<i>ConnectorService</i>, <i>AuthService</i>, <i>ProviderService</i> form the use-case "
        "layer.<br/>"
        "<b>Ports</b>: <i>KnowledgeStorePort</i>, <i>SearchEnginePort</i>, "
        "<i>EmbeddingProviderPort</i>, <i>LlmProviderPort</i>, <i>RerankerPort</i>, "
        "<i>SandboxPort</i>, <i>ObjectStorePort</i>, <i>JobQueuePort</i>, <i>OcrBackendPort</i>, "
        "<i>AgentStorePort</i>, <i>DeploymentStorePort</i>.<br/>"
        "<b>Adapters</b>: SQLAlchemy (Postgres / SQLite), S3 / local-fs object store, "
        "OpenSearch / in-memory search engine, Ollama / OpenAI / Anthropic / Gemini LLMs, "
        "Tesseract / Ollama-vision OCR, subprocess sandbox, ARQ / inline job queues.",
        BODY))

    story.append(Paragraph("Data plane", H2))
    story.append(Paragraph(
        "Documents are ingested through <i>IngestionService</i> which streams uploads to the "
        "object store and enqueues a parse job. Workers parse text, run optional OCR on image-"
        "only pages, chunk according to one of four templates (general, sentence-window, "
        "small-to-big, qa), embed each chunk, index into the search engine, and optionally "
        "extract a knowledge graph of subject-predicate-object triples via the configured "
        "LLM provider. All chunk metadata, parent links, and graph triples are persisted in "
        "Postgres / SQLite alongside the document record.",
        BODY))

    story.append(Paragraph("Control plane", H2))
    story.append(Paragraph(
        "FastAPI exposes 17 HTTP route modules. A <b>token-bucket rate limiter</b>, "
        "<b>structured JSON logger</b>, <b>Prometheus metrics middleware</b>, and "
        "<b>session/JWT authentication</b> wrap every request. The <b>ConnectorScheduler</b> "
        "runs a 30-second tick loop pulling new files from configured connectors. Background "
        "jobs run either inline (development) or via ARQ + Redis (production).",
        BODY))
    story.append(PageBreak())

    # ---- 4. FEATURE INVENTORY ----
    story.append(Paragraph("4. Feature Inventory", H1))
    story.append(Paragraph(
        "Each subsection enumerates the discrete features within a domain area together with a "
        "current-state assessment. <b>Done</b> means production-ready and tested. <b>Partial</b> "
        "means functional but missing edge-cases, polish, or a production-grade adapter. "
        "<b>Missing</b> means the feature is a known gap relative to industry standard.",
        BODY))

    # 4.1 AUTH
    story.append(Paragraph("4.1 Authentication, Authorization & Security", H2))
    story.append(feature_table([
        ("Email + password login", "done", "bcrypt hashing, AUTH_SECRET-signed JWT-style session tokens"),
        ("Session token revocation", "done", "Per-token jti embedded; logout inserts into RevokedTokenRecord blocklist"),
        ("Password reset flow", "done", "Single-use tokens, bcrypt-hashed, 1-hour TTL"),
        ("API keys", "done", "omsk_-prefixed; per-key rate limits; revocation"),
        ("Bootstrap admin", "done", "Auto-created from env on first start; idempotent"),
        ("Role-based access (OWNER/ADMIN/EDITOR/VIEWER)", "done", "Tenant-scoped; permission map in security/permissions.py"),
        ("Per-collection RBAC", "done", "Independent roles per collection_id"),
        ("Encryption-at-rest for secrets", "done", "ENCRYPTION_KEY-driven SecretBox (Fernet)"),
        ("Rate limiting", "done", "Token-bucket per user/key/IP; configurable"),
        ("Audit log", "partial", "Events recorded but page hardcoded LIMIT 100; needs pagination"),
        ("OAuth / SSO (Google, GitHub, OIDC)", "missing", "No third-party identity provider integration"),
        ("MFA / 2FA (TOTP)", "missing", "No second-factor enforcement"),
        ("Brute-force lockout", "partial", "Rate limiter mitigates; no explicit account lockout after N failures"),
        ("CSRF protection", "partial", "Cookie SameSite=Lax; no double-submit token for non-API consumers"),
        ("Content-Security-Policy headers", "missing", "Not yet emitted by FastAPI middleware"),
        ("Penetration test / SOC 2 audit", "missing", "Not yet performed"),
    ]))

    # 4.2 KNOWLEDGE
    story.append(Paragraph("4.2 Knowledge Base — Collections, Documents, Ingestion", H2))
    story.append(feature_table([
        ("Collections CRUD", "done", "Per-tenant; embedding model, chunk template, top-k, vector weight all configurable"),
        ("Document upload (single)", "done", "Streams to object store; sha256-keyed; supports up to 100 MiB by default"),
        ("Bulk upload", "done", "Up to 20 files in one call"),
        ("Document versioning (upsert by name)", "done", "Identical content dedups; changed content updates in-place + reindexes"),
        ("Document tags + by-tag listing", "done", "Per-tenant tag namespace"),
        ("Re-index on demand", "done", "POST /documents/{id}/reindex with optional template/model swap"),
        ("PDF parser", "done", "PyPDF + optional OCR fallback for image-only pages"),
        ("DOCX, HTML, plain-text parsers", "done", "Pluggable ParserRegistry; resolved by mime + filename"),
        ("Image / scanned-PDF OCR", "done", "Tesseract + Ollama-vision (LLaVA) backends"),
        ("Chunk templates", "done", "general, sentence-window, small-to-big (parent), qa"),
        ("Parent-chunk expansion at retrieval", "done", "Child hits replaced by their parent for richer context"),
        ("Knowledge-graph triple extraction", "done", "LLM-driven; per-collection and per-document listing"),
        ("Tenant-level quotas (docs, storage)", "done", "Configurable; enforced at upload time"),
        ("Object store: S3-compatible + local-fs", "done", "Adapter interface; works with MinIO / R2"),
        ("Object store: Azure Blob / GCS native", "missing", "Only S3-style endpoint and local-fs supported"),
        ("Bulk delete / re-tag UI", "missing", "Frontend has single-document actions only"),
        ("Document export / portability", "missing", "No bundled export of collection + chunks + graph"),
    ]))

    # 4.3 RETRIEVAL
    story.append(Paragraph("4.3 Search & Retrieval Pipeline", H2))
    story.append(feature_table([
        ("Vector search (cosine)", "done", "Dense embeddings via Ollama / nomic-embed-text"),
        ("Sparse search (Okapi BM25)", "done", "Real BM25 with k1=1.2, b=0.75; incremental df tracking"),
        ("Hybrid fusion (RRF)", "done", "Reciprocal Rank Fusion with k=60; vector_weight smoothly interpolates"),
        ("Reranking", "done", "Cross-encoder (BAAI/bge-reranker-base) + paired-embedding fallback"),
        ("MMR diversification", "done", "Maximal Marginal Relevance to break redundancy"),
        ("Parent-chunk expansion", "done", "Small-to-big template upgrades child hits to parents"),
        ("Graph augmentation", "done", "Entities in query trigger triple lookups; injected into hits"),
        ("Query rewriting", "done", "LLM-driven follow-up rewrite for conversational continuity"),
        ("Result caching (Redis / in-process)", "done", "RETRIEVAL_CACHE_TTL_SECONDS-controlled; tenant-scoped keys"),
        ("Search engine: OpenSearch", "done", "BM25 query DSL + dense kNN script-score"),
        ("Search engine: in-memory", "done", "Pickle-snapshot persistence on shutdown / upsert"),
        ("Search engine: pgvector / Pinecone / Weaviate", "missing", "Adapter interface ready; no implementation yet"),
        ("Multi-modal retrieval (image + text)", "missing", "Embeddings are text-only"),
        ("Hypothetical Document Embeddings (HyDE)", "missing", "No HyDE-style query expansion"),
        ("Streaming retrieval / progress events", "missing", "Retrieval is request/response; no SSE for partial hits"),
    ]))

    # 4.4 CHAT
    story.append(Paragraph("4.4 Chat & Conversational AI", H2))
    story.append(feature_table([
        ("Streaming chat (SSE)", "done", "Server-sent events; supports cancel + partial citations"),
        ("Conversation persistence", "done", "Postgres + Pydantic models; pinning supported"),
        ("Citation tracking per message", "done", "Citations stored as JSON column; no N+1"),
        ("Follow-up query rewriting", "done", "LLM-driven; falls back gracefully"),
        ("Provider switching mid-conversation", "done", "model_provider + model_name overrides per request"),
        ("LLM provider: Ollama (local)", "done", "Default; supports any local model"),
        ("LLM provider: OpenAI", "done", "Streaming chat completion"),
        ("LLM provider: Anthropic", "done", "Messages API streaming"),
        ("LLM provider: Gemini", "done", "Streaming generate_content"),
        ("Custom system prompt per collection", "done", "Persisted on collection record"),
        ("Per-tenant model allow-list", "done", "ProviderService manages allowed models"),
        ("Conversation export (JSON / Markdown)", "missing", "No bulk export"),
        ("Multi-user conversation (collab)", "missing", "Conversations are single-user"),
        ("Branching / forking conversations", "missing", "No tree structure; linear messages only"),
        ("Voice input / output", "missing", "No STT/TTS integration"),
    ]))

    # 4.5 AGENTS
    story.append(Paragraph("4.5 Agents & Workflow Engine", H2))
    story.append(feature_table([
        ("Visual workflow definition", "done", "JSON graph: nodes + edges + retrieval / generation / message / code / end"),
        ("Default agent template", "done", "5-node graph: start → retrieve → generate → message → end"),
        ("Code node with sandboxed Python", "done", "Subprocess sandbox; user_input + context_text injected"),
        ("Per-agent versioning (definition JSON)", "done", "Versioned via update; no formal version history"),
        ("Run history with events log", "done", "Every node emits node.start / node.output / node.error events"),
        ("Token usage estimation", "done", "tiktoken with char-ratio fallback"),
        ("Publish / unpublish toggle", "done", "Boolean flag on agent record"),
        ("Multi-step tool use (function calling)", "partial", "Code node yes; OpenAI/Anthropic native tool-calling not wired"),
        ("Parallel branches in graph", "missing", "Walker is single-path; no fan-out/join"),
        ("Human-in-the-loop pause / resume", "missing", "Runs are atomic; no pause checkpoint"),
        ("Time-travel / replay", "missing", "Events are logged but UI replay is not implemented"),
        ("Agent marketplace / sharing", "missing", "No import-from-URL or template registry"),
    ]))

    # 4.6 CONNECTORS
    story.append(Paragraph("4.6 Connectors — Data Ingestion Sources", H2))
    story.append(feature_table([
        ("Local-folder connector", "done", "Watches a path; ingests new / changed files"),
        ("S3 connector", "done", "Lists objects; tracks last_synced_etag"),
        ("Web crawler connector", "done", "Depth-limited BFS; domain whitelist; pattern filters"),
        ("Connector scheduler", "done", "30-second tick loop; per-connector cron"),
        ("Distributed scheduler lock", "missing", "Two API instances would double-ingest; needs Redis lock"),
        ("Google Drive connector", "missing", "OAuth + Drive API not wired"),
        ("SharePoint / OneDrive connector", "missing", "MS Graph not wired"),
        ("Confluence / Notion / Slack", "missing", "No SaaS-knowledge-source integrations yet"),
        ("Database-table connector", "missing", "No JDBC / SQLAlchemy connector to ingest table rows"),
        ("Connector dry-run / preview", "partial", "Sync-now button; no preview UI"),
    ]))

    # 4.7 DEPLOYMENTS
    story.append(Paragraph("4.7 Deployments — Public Chat Surface", H2))
    story.append(feature_table([
        ("Slug-based deployment URLs", "done", "/c/{slug}; validated, unique"),
        ("Anonymous chat allowed flag", "done", "Per-deployment toggle"),
        ("Per-deployment rate limit", "done", "Independent of tenant rate limit"),
        ("System-prompt override", "done", "Overrides the underlying collection / agent prompt"),
        ("Deployment quotas (msg/day, tokens/day)", "done", "Enforced at request time"),
        ("Pause / publish state", "done", "Toggle from admin UI"),
        ("Iframe-friendly CORS preset", "partial", "CORS configurable but no embed wizard"),
        ("Branding / theming per deployment", "missing", "No logo / color picker"),
        ("Deployment analytics (msg count, latency)", "partial", "Counted in metrics but no per-deployment dashboard"),
        ("Custom domain mapping", "missing", "Slug only; no DNS-level mapping"),
    ]))

    # 4.8 SANDBOX
    story.append(Paragraph("4.8 Sandbox / Code Execution", H2))
    story.append(feature_table([
        ("Subprocess sandbox", "done", "Resource-limited Python; stdout / stderr / artifacts captured"),
        ("Timeout enforcement", "done", "Per-call timeout_seconds; default configurable"),
        ("Stderr capture", "done", "Structured separate from stdout"),
        ("Artifact files", "done", "/tmp scratch dir copied back as bytes"),
        ("CPU / memory hard limits", "partial", "Subprocess inherits parent limits; needs cgroup / Docker isolation"),
        ("Network policy enforcement", "missing", "Subprocess can hit network freely"),
        ("Container sandbox (Docker / gVisor)", "missing", "Only subprocess backend; needs hardened backend"),
        ("Multi-language support (JS, Bash)", "missing", "Python 3 only"),
    ]))

    # 4.9 OBSERVABILITY
    story.append(Paragraph("4.9 Observability & Operations", H2))
    story.append(feature_table([
        ("Structured JSON logs", "done", "_JsonFormatter; LOG_LEVEL / LOG_FORMAT env-driven"),
        ("Prometheus /metrics endpoint", "done", "request count / latency / rate-limit / token usage"),
        ("Health check endpoint", "done", "/v1/health returns environment + status"),
        ("Audit events", "done", "auth.login, deployment.create, etc. recorded to DB"),
        ("Distributed tracing (OpenTelemetry)", "missing", "No spans emitted yet"),
        ("Grafana dashboards", "missing", "Metrics emitted but no dashboard JSON shipped"),
        ("Alerts / alert rules", "missing", "Prometheus rules not yet authored"),
        ("Error reporting (Sentry / Rollbar)", "missing", "No external error sink"),
        ("Per-tenant cost dashboard", "missing", "Token usage tracked but not aggregated by tenant cost"),
        ("Retrieval relevance metrics over time", "missing", "No long-running quality dashboard"),
    ]))

    # 4.10 MULTI-TENANCY & RBAC
    story.append(Paragraph("4.10 Multi-Tenancy & RBAC", H2))
    story.append(feature_table([
        ("Tenant isolation (row-level)", "done", "Every query scoped by tenant_id; verified by 165 tests"),
        ("Tenant quotas (documents, storage)", "done", "Enforced at upload time"),
        ("Tenant-scoped tokens / API keys", "done", "Cannot cross-tenant"),
        ("Role permission matrix", "done", "OWNER / ADMIN / EDITOR / VIEWER mapped to actions"),
        ("Per-collection ACL", "done", "User can be EDITOR on one collection, VIEWER on another"),
        ("Team grouping", "done", "Teams CRUD endpoints"),
        ("Invitations by email", "missing", "User creation is admin-only; no invite-link"),
        ("SCIM provisioning", "missing", "No directory-sync"),
        ("Tenant suspension / soft-delete", "partial", "Tenant exists but no admin UI to disable"),
    ]))

    # 4.11 FRONTEND
    story.append(Paragraph("4.11 Frontend (React UI)", H2))
    story.append(feature_table([
        ("Login / logout", "done", "JWT stored; auto-refreshed"),
        ("Knowledge page (collections + docs)", "done", "Full CRUD; upload; tags; reindex"),
        ("Chat page (streaming)", "done", "SSE consumer; citation popovers"),
        ("Agents page (list + run)", "done", "Run history, output rendering"),
        ("Search page (manual retrieval)", "done", "Hybrid retrieval inspector"),
        ("Deployments page", "done", "CRUD; copy public link"),
        ("Admin page", "done", "Users, providers, audit"),
        ("Connectors UI", "done", "Kind-aware config templates; sync-now button"),
        ("Dark mode", "missing", "Light theme only"),
        ("Mobile / responsive layout", "partial", "Desktop-first; works at >= 768px"),
        ("Accessibility (WCAG 2.1 AA)", "partial", "Semantic HTML; not formally audited"),
        ("Keyboard shortcuts", "missing", "No ⌘+K palette"),
        ("i18n / translations", "missing", "Hardcoded English"),
        ("E2E tests (Playwright)", "missing", "Vitest unit only; no browser harness"),
        ("Storybook / component catalogue", "missing", "No isolated component browser"),
    ]))

    story.append(PageBreak())

    # ---- 5. RECENT IMPROVEMENTS ----
    story.append(Paragraph("5. Recent Improvements (This Iteration)", H1))
    story.append(Paragraph(
        "The following capabilities were added or hardened in the most recent development cycle:",
        BODY))
    improvements = [
        ("Real Okapi BM25",
         "Replaced a placeholder term-frequency proxy with a proper BM25 implementation: incremental df tracking, "
         "per-tenant total tokens, average document length, k1/b parameters."),
        ("Reciprocal Rank Fusion",
         "Hybrid scores combined via RRF with k=60 instead of simple weighted-sum, removing scale mismatches "
         "between cosine similarity and BM25 magnitudes."),
        ("Snapshot persistence for in-memory search",
         "InMemorySearchEngine now serializes to pickle on every upsert and on shutdown; restored on next boot. "
         "Removes the cold-start re-index requirement in dev."),
        ("Session token revocation (logout that actually logs out)",
         "Added a jti claim to every issued token; logout writes the jti to a RevokedTokenRecord blocklist; "
         "every authentication checks it."),
        ("Password reset flow",
         "Single-use, bcrypt-hashed reset tokens with 1-hour TTL. Round-trip integration test in CI."),
        ("Web crawler connector",
         "Depth-limited async BFS over httpx; domain whitelist; include / exclude regex; up to 500 pages per run."),
        ("Sandboxed Python in agents",
         "Code nodes execute inside the subprocess sandbox; receive user_input and context_text variables; "
         "stdout becomes the next-node answer."),
        ("Structured JSON logging",
         "Drop-in replacement for the default formatter. Level / format / third-party verbosity all env-driven."),
        ("Token-usage estimation",
         "tiktoken when available, char-ratio fallback otherwise. Used by AgentService to populate run.usage."),
        ("Retrieval result cache",
         "In-process TTL cache (with Redis upgrade path). Tenant-scoped keys; opt-in via "
         "RETRIEVAL_CACHE_TTL_SECONDS."),
        ("Document versioning",
         "Re-uploading an existing filename now upserts: identical content dedups silently; changed content "
         "updates the record in-place, clears the search index, and re-enqueues parsing."),
        ("CI/CD pipeline",
         "GitHub Actions: backend matrix (3.11 + 3.12), frontend type-check + tests, integration smoke job, "
         "codecov upload."),
        ("Frontend test setup",
         "Vitest + Testing Library configured; jsdom; 7 client-API tests and a clear path for component tests."),
    ]
    for title, desc in improvements:
        story.append(Paragraph(f"<b>{title}.</b> {desc}", BODY))

    story.append(PageBreak())

    # ---- 6. GAP ANALYSIS ----
    story.append(Paragraph("6. Gap Analysis vs. Industry Grade", H1))
    story.append(Paragraph(
        "An honest comparison against what enterprise customers expect from a RAG / agent "
        "platform in 2026. Each gap below has a clear remediation path; none are architectural "
        "blockers.",
        BODY))

    story.append(Paragraph("Critical (must-have before paid customers)", H2))
    for item in [
        "<b>SSO / OIDC</b>: customers will refuse to provision local users. Need Google, Microsoft, GitHub, generic OIDC.",
        "<b>MFA / 2FA</b>: TOTP at minimum; WebAuthn ideal.",
        "<b>Distributed scheduler lock</b>: connector_scheduler currently assumes one API replica.",
        "<b>Kubernetes manifests</b>: no Helm chart, no production deployment template.",
        "<b>Audit log pagination + export</b>: hardcoded LIMIT 100 fails at scale.",
        "<b>Container-isolated sandbox</b>: subprocess sandbox is acceptable for trusted code only.",
        "<b>Backup / restore documentation</b>: no formal runbook for disaster recovery.",
    ]:
        story.append(Paragraph("• " + item, BULLET))

    story.append(Paragraph("Important (within first 6 months)", H2))
    for item in [
        "<b>Grafana dashboards + alert rules</b>: metrics exist; need shipped JSON dashboards.",
        "<b>OpenTelemetry tracing</b>: requests across HTTP → worker → DB → search currently un-correlated.",
        "<b>Sentry / error sink</b>: 500s only land in logs.",
        "<b>Bulk operations UI</b>: no multi-select for documents / agents / collections.",
        "<b>Conversation + agent export</b>: data portability is table-stakes.",
        "<b>SaaS connectors</b>: Google Drive, SharePoint, Notion, Confluence, Slack.",
        "<b>Image-modal retrieval</b>: text-only embeddings limit RAGFlow parity.",
        "<b>Native tool / function calling for OpenAI + Anthropic</b>: code node only goes so far.",
        "<b>Per-tenant cost dashboard</b>: tokens are counted; not aggregated per tenant in $.",
        "<b>WCAG 2.1 audit + remediation</b>: enterprises ask for a VPAT.",
        "<b>E2E browser tests (Playwright)</b>: catches regressions vitest cannot.",
        "<b>Dark mode + theming</b>: standard expectation now.",
    ]:
        story.append(Paragraph("• " + item, BULLET))

    story.append(Paragraph("Nice-to-have (year-one roadmap)", H2))
    for item in [
        "Branching / forking conversations.",
        "Voice (STT / TTS) integration.",
        "Agent marketplace / shareable templates with import-from-URL.",
        "HyDE-style query expansion.",
        "pgvector + Pinecone + Weaviate adapters.",
        "Custom domain mapping for deployments.",
        "Iframe embed wizard with theming controls.",
        "i18n / locale support.",
        "Storybook component catalog.",
        "SCIM directory provisioning.",
    ]:
        story.append(Paragraph("• " + item, BULLET))

    story.append(PageBreak())

    # ---- 7. MILESTONE ROADMAP ----
    story.append(Paragraph("7. Milestone Roadmap", H1))
    story.append(Paragraph(
        "A concrete sequencing of remaining work into shippable milestones. Each milestone is "
        "scoped to roughly 2&ndash;4 weeks for a small team and ends in a demonstrably better "
        "product.",
        BODY))

    milestones = [
        ("M14 — Production Hardening (2 weeks)",
         "Make the platform safe to deploy in front of a paying customer.",
         [
             "Distributed lock for ConnectorScheduler (Redis SETNX with TTL).",
             "Kubernetes manifests + Helm chart with sane defaults.",
             "Backup / restore runbook (Postgres dump + object-store sync).",
             "Audit log pagination + cursor-based listing endpoint.",
             "Container-isolated sandbox backend (Docker / gVisor) behind SANDBOX_KIND env.",
             "CSP + HSTS security headers middleware.",
             "Account lockout after N failed logins.",
         ]),
        ("M15 — Identity & Access (2 weeks)",
         "Meet enterprise SSO / MFA requirements.",
         [
             "Generic OIDC provider integration (Authlib).",
             "Google + Microsoft + GitHub social-login presets.",
             "TOTP-based MFA with recovery codes.",
             "WebAuthn / passkey support (stretch).",
             "User invitation flow with one-time email link.",
             "SCIM 2.0 endpoint for directory sync (stretch).",
         ]),
        ("M16 — Observability & Cost (2 weeks)",
         "Make the running system understandable and economical.",
         [
             "OpenTelemetry tracing through HTTP → worker → DB → search.",
             "Shipped Grafana dashboards (4 dashboards: API, retrieval, ingestion, agents).",
             "Prometheus alert rules (error rate, latency, queue depth).",
             "Sentry integration for unhandled exceptions.",
             "Per-tenant cost dashboard (tokens × $/1k).",
             "Retrieval-quality metrics over time (NDCG, hit-rate).",
         ]),
        ("M17 — Connector Library Expansion (3 weeks)",
         "Match RAGFlow's data-source catalog.",
         [
             "Google Drive connector (OAuth + Drive API).",
             "SharePoint / OneDrive connector (MS Graph).",
             "Notion connector.",
             "Confluence connector.",
             "Slack connector (channels + threads).",
             "JDBC / SQLAlchemy table connector.",
             "Connector dry-run preview UI.",
         ]),
        ("M18 — UX & Accessibility (2 weeks)",
         "Polish that makes the product feel finished.",
         [
             "Dark mode across all pages.",
             "Bulk operations (multi-select, batch delete / tag / re-index).",
             "Conversation + agent export (JSON + Markdown).",
             "WCAG 2.1 AA audit + remediation.",
             "Keyboard shortcut palette (⌘+K).",
             "i18n / locale framework + English/Spanish strings.",
             "Playwright E2E test suite for the 5 critical flows.",
             "Storybook setup for the design system.",
         ]),
        ("M19 — Advanced Retrieval (3 weeks)",
         "Push retrieval quality past RAGFlow's defaults.",
         [
             "Multi-modal embeddings (text + image) via CLIP-class models.",
             "HyDE query expansion with toggle in the retrieval UI.",
             "pgvector adapter for the SearchEnginePort.",
             "Pinecone + Weaviate adapters.",
             "Streaming retrieval (SSE for partial hits).",
             "Native tool / function-calling pass-through for OpenAI + Anthropic.",
             "Conversation branching / forking model.",
         ]),
        ("M20 — Agent Platform (3 weeks)",
         "Make agents the differentiator.",
         [
             "Parallel branches in agent graphs (fan-out / join).",
             "Human-in-the-loop pause / resume nodes.",
             "Time-travel replay over event log.",
             "Agent template marketplace with import-from-URL.",
             "Multi-language sandbox (JavaScript, Bash).",
             "Network-isolated sandbox via gVisor.",
             "Agent run cost per execution + alerting on overrun.",
         ]),
    ]

    for title, sub, bullets in milestones:
        story.append(Paragraph(title, MILESTONE_TITLE))
        story.append(Paragraph(sub, BODY))
        for b in bullets:
            story.append(Paragraph("• " + b, BULLET))
        story.append(Spacer(1, 0.1 * inch))

    story.append(PageBreak())

    # ---- 8. CONCLUSION ----
    story.append(Paragraph("8. Conclusion", H1))
    story.append(Paragraph(
        "Omni-AI is in a stronger position than its line count would suggest. The hexagonal "
        "architecture has held up across 13 migrations and 17 plugin types without forcing any "
        "rewrites. The retrieval pipeline is genuinely competitive with RAGFlow on the metrics "
        "that matter (hybrid search, RRF, MMR, reranking, parent-chunk expansion, knowledge-"
        "graph augmentation). The remaining gap is mostly <i>operational</i> rather than "
        "<i>capability</i>: SSO, distributed coordination, dashboards, and the polish layer.",
        BODY))
    story.append(Paragraph(
        "If the team executes the seven milestones above (M14&ndash;M20, roughly 17 weeks of "
        "concentrated effort) the platform will be ahead of RAGFlow on agent capabilities and "
        "at parity on retrieval, with first-class enterprise identity, observability, and "
        "deployability. That is a defensible v1.0.",
        BODY))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("— End of report.",
                           ParagraphStyle("end", parent=BODY, alignment=TA_CENTER, textColor=GREY)))

    return story


def main() -> None:
    out_path = Path("omniai_industry_grade_report.pdf")
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Omni-AI Industry-Grade Audit Report",
        author="Omni-AI Engineering",
    )
    story = build_story()
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    size_kb = out_path.stat().st_size // 1024
    print(f"Wrote {out_path} ({size_kb} KB)")


if __name__ == "__main__":
    main()
