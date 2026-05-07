"""
OmniAI -- Complete Project Guide
Covers every feature across all milestones.
Run:  python generate_full_guide_pdf.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
import os, sys

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OmniAI_Complete_Guide.pdf")

# ── Colour palette ─────────────────────────────────────────────────────────────
INDIGO   = colors.HexColor("#4F46E5")
VIOLET   = colors.HexColor("#7C3AED")
TEAL     = colors.HexColor("#0D9488")
AMBER    = colors.HexColor("#D97706")
ROSE     = colors.HexColor("#E11D48")
OCEAN    = colors.HexColor("#0369A1")
FOREST   = colors.HexColor("#166534")
SLATE    = colors.HexColor("#334155")
LIGHT_BG = colors.HexColor("#F8FAFC")
CARD_BG  = colors.HexColor("#EFF6FF")
CODE_BG  = colors.HexColor("#1E293B")
CODE_FG  = colors.HexColor("#E2E8F0")
MINT_BG  = colors.HexColor("#F0FDF4")
AMBER_BG = colors.HexColor("#FFFBEB")
ROSE_BG  = colors.HexColor("#FFF1F2")
OCEAN_BG = colors.HexColor("#F0F9FF")
WHITE    = colors.white
GREY     = colors.HexColor("#64748B")
DARK     = colors.HexColor("#0F172A")

# ── Paragraph styles ───────────────────────────────────────────────────────────
def S(name, **kw): return ParagraphStyle(name, **kw)

H1   = S("H1",   fontName="Helvetica-Bold",    fontSize=20, textColor=INDIGO,  leading=27, spaceBefore=16, spaceAfter=6)
H2   = S("H2",   fontName="Helvetica-Bold",    fontSize=14, textColor=VIOLET,  leading=20, spaceBefore=12, spaceAfter=5)
H3   = S("H3",   fontName="Helvetica-Bold",    fontSize=11, textColor=TEAL,    leading=16, spaceBefore=8,  spaceAfter=3)
BODY = S("Body", fontName="Helvetica",         fontSize=10, textColor=SLATE,   leading=15, spaceAfter=4, alignment=TA_JUSTIFY)
BB   = S("BB",   fontName="Helvetica-Bold",    fontSize=10, textColor=DARK,    leading=15, spaceAfter=3)
BUL  = S("Bul",  fontName="Helvetica",         fontSize=10, textColor=SLATE,   leading=15, leftIndent=14, firstLineIndent=-8, spaceAfter=2)
CODE = S("Code", fontName="Courier",           fontSize=8,  textColor=CODE_FG, leading=12, backColor=CODE_BG,
         leftIndent=8, rightIndent=8, spaceBefore=3, spaceAfter=3, borderPad=4)
NOTE = S("Note", fontName="Helvetica-Oblique", fontSize=9.5, textColor=AMBER,  leading=14, spaceAfter=3)

W = 15.5 * cm   # usable content width

# ── Low-level helpers ──────────────────────────────────────────────────────────
def sp(h=0.25):  return Spacer(1, h * cm)
def hr(c=INDIGO, t=1.0): return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=4)
def p(text, style=BODY): return Paragraph(text, style)
def h1(t): return Paragraph(t, H1)
def h2(t): return Paragraph(t, H2)
def h3(t): return Paragraph(t, H3)
def bold(t): return Paragraph(t, BB)

def bul(items):
    return [Paragraph(f"&bull;  {i}", BUL) for i in items]

def num(items):
    return [Paragraph(f"<b>{n}.</b>  {i}", BUL) for n, i in enumerate(items, 1)]

def code(*lines):
    joined = "<br/>".join(
        l.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace(" ","&nbsp;")
        for l in lines
    )
    return Paragraph(joined, CODE)

def box(text, bg=CARD_BG, border=INDIGO, label=""):
    inner = S(f"IB_{id(text)}", fontName="Helvetica", fontSize=9.5, textColor=DARK, leading=14)
    if label: text = f"<b>{label}</b>  {text}"
    tbl = Table([[Paragraph(text, inner)]], colWidths=[W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("BOX",           (0,0),(-1,-1), 1.5, border),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
    ]))
    return tbl

def tbl(rows, widths=None):
    widths = widths or [4.5*cm, 11*cm]
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  INDIGO),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  8.5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LIGHT_BG]),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1),(-1,-1), 8),
        ("TEXTCOLOR",     (0,1),(-1,-1), SLATE),
        ("GRID",          (0,0),(-1,-1), 0.35, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    return t

def sec_hdr(title, color):
    sty = S(f"SH_{id(title)}", fontName="Helvetica-Bold", fontSize=17, textColor=WHITE, leading=23)
    t = Table([[Paragraph(title, sty)]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
    ]))
    return t

def mini_hdr(title, color):
    """Smaller in-section header band."""
    sty = S(f"MH_{id(title)}", fontName="Helvetica-Bold", fontSize=11, textColor=WHITE, leading=16)
    t = Table([[Paragraph(title, sty)]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    return t

# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════
def cover():
    TI = S("CT",  fontName="Helvetica-Bold", fontSize=42, textColor=WHITE,   leading=52, alignment=TA_CENTER)
    TS = S("CS",  fontName="Helvetica-Bold", fontSize=22, textColor=colors.HexColor("#A5B4FC"), leading=28, alignment=TA_CENTER)
    TD = S("CD",  fontName="Helvetica-Oblique", fontSize=12, textColor=colors.HexColor("#CBD5E1"), leading=18, alignment=TA_CENTER)
    TV = S("CV",  fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#818CF8"), leading=15, alignment=TA_CENTER)

    banner = Table([
        [Paragraph("OmniAI", TI)],
        [Paragraph("Complete Platform Guide", TS)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("Every feature. Every API. Simply explained.", TD)],
        [Spacer(1, 0.2*cm)],
        [Paragraph("Milestones 1 through 20  --  Full Reference", TV)],
        [Spacer(1, 0.5*cm)],
    ], colWidths=[W])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), INDIGO),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))

    ML = S("ML", fontName="Helvetica-Bold", fontSize=13, textColor=WHITE,   alignment=TA_CENTER)
    MT = S("MT", fontName="Helvetica-Bold", fontSize=10, textColor=DARK)
    MD = S("MD", fontName="Helvetica",      fontSize=9,  textColor=GREY)

    ms = [
        ["Area",              "What you get"],
        ["Document Ingestion","Upload PDFs, Word docs, HTML; automatic parsing and indexing"],
        ["Smart Search",      "Vector + BM25 hybrid search, HyDE, reranking, streaming, tool calling"],
        ["Chat & RAG",        "Multi-turn conversations with citations, forking, export"],
        ["LLM Providers",     "Anthropic Claude, OpenAI GPT, Google Gemini, local Ollama"],
        ["Agents",            "DAG-based AI workflows: fan-out, HITL, replay, templates, cost tracking"],
        ["Code Sandbox",      "Run Python, JavaScript, Bash safely (subprocess / Docker / gVisor)"],
        ["Deployments",       "Public chat pages and webhooks with rate limits and daily quotas"],
        ["Connectors",        "Sync from Google Drive, SharePoint, Notion, Confluence, Slack, S3"],
        ["Identity & Access", "MFA (TOTP), OIDC (Google/GitHub/Microsoft), teams, RBAC, invitations"],
        ["Observability",     "Cost dashboards, retrieval quality, audit logs, Prometheus, OpenTelemetry"],
    ]
    ms_tbl = Table(ms, colWidths=[4.5*cm, 11*cm])
    ms_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  DARK),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [MINT_BG, CARD_BG, AMBER_BG, ROSE_BG, OCEAN_BG,
                                          MINT_BG, CARD_BG, AMBER_BG, ROSE_BG, OCEAN_BG]),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1),(-1,-1), 9),
        ("TEXTCOLOR",     (0,1),(-1,-1), SLATE),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))

    return [banner, sp(0.5), ms_tbl, PageBreak()]


# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ══════════════════════════════════════════════════════════════════════════════
def toc():
    TH = S("TH", fontName="Helvetica-Bold", fontSize=11, textColor=INDIGO,  leading=17, spaceBefore=8)
    TI = S("TI", fontName="Helvetica",      fontSize=9.5, textColor=SLATE,  leading=15)

    sections = [
        ("1.  Getting Started",           ["Installation & first run", "Default admin credentials", "Project layout"]),
        ("2.  Core Concepts",             ["Tenants & multi-tenancy", "Collections, Documents, Chunks"]),
        ("3.  Document Management",       ["Upload files", "Bulk operations", "Tags & reindex", "Knowledge graph"]),
        ("4.  Search & Retrieval",        ["Basic semantic search", "BM25 keyword search", "HyDE expansion",
                                           "Streaming search", "Tool calling", "Multi-modal (images)", "Reranking", "Caching"]),
        ("5.  Chat & Conversations",      ["Create & manage conversations", "Send messages with RAG",
                                           "Regenerate responses", "Fork conversations", "Export conversations"]),
        ("6.  LLM Providers",             ["Anthropic Claude", "OpenAI GPT", "Google Gemini", "Ollama (local)"]),
        ("7.  Agent Platform",            ["Create agents (DAG definition)", "Run agents", "Parallel fan-out / join",
                                           "Human-in-the-Loop (pause & resume)", "Time-travel replay",
                                           "Template marketplace", "Multi-language code nodes", "gVisor sandbox",
                                           "Cost tracking & alerts", "Export agent runs"]),
        ("8.  Deployments",               ["Public chat pages", "Webhook deployments", "Rate limits & quotas"]),
        ("9.  Connectors",                ["Local folder", "Amazon S3", "Google Drive", "SharePoint",
                                           "Notion", "Confluence", "Slack"]),
        ("10. Identity & Access",         ["Registration & login", "API keys", "MFA (TOTP)", "OIDC (Google / GitHub / Microsoft)",
                                           "Teams & roles", "Invitations", "RBAC on collections"]),
        ("11. Observability",             ["LLM cost dashboard", "Retrieval quality metrics", "Audit log",
                                           "Prometheus metrics", "OpenTelemetry tracing", "Sentry"]),
        ("12. Security",                  ["Rate limiting", "Account lockout", "Encryption at rest", "Environment security"]),
        ("13. Configuration Reference",   ["All environment variables with defaults"]),
        ("14. API Quick Reference",       ["All 80+ endpoints at a glance"]),
    ]

    story = [h1("Contents"), hr(), sp(0.1)]
    for title, items in sections:
        story.append(Paragraph(title, TH))
        for item in items:
            story.append(Paragraph(f"        {item}", TI))
        story.append(sp(0.1))
    story.append(PageBreak())
    return story


# ══════════════════════════════════════════════════════════════════════════════
# 1. GETTING STARTED
# ══════════════════════════════════════════════════════════════════════════════
def sec_getting_started():
    s = [sec_hdr("1.  Getting Started", INDIGO), sp(0.25)]

    s += [h2("What is OmniAI?")]
    s += [p("OmniAI is an <b>open-source, multi-tenant AI platform</b>. Think of it as a private "
            "ChatGPT that you run on your own computer or server -- one that can read <i>your</i> "
            "documents, remember conversations, and run automated AI workflows called <b>Agents</b>. "
            "Everything stays on your infrastructure. Nothing is sent to a third party unless you "
            "connect your own OpenAI or Anthropic key.")]
    s += [sp(0.15), box(
        "<b>Key idea:</b>  You upload your documents (PDFs, Word files, web pages). "
        "OmniAI reads them, turns them into searchable 'chunks', and lets any AI model "
        "answer questions about them -- with references to the exact passages it used.",
        bg=MINT_BG, border=TEAL
    ), sp(0.2)]

    s += [h2("Installation (Developer Setup)")]
    s += bul([
        "<b>Requirements:</b>  Python 3.11+, Node.js 18+, Git.",
        "<b>Clone the repo</b>  and enter the backend folder.",
        "<b>Create a virtual environment</b>  and install dependencies.",
        "<b>Copy</b> <tt>.env.example</tt>  to  <tt>.env</tt>  (no changes needed for local dev).",
        "<b>Start the server</b> -- it auto-creates the database and default admin user on first run.",
    ])
    s += [sp(0.1), code(
        "git clone https://github.com/your-org/omniai.git",
        "cd omniai/backend",
        "python -m venv .venv && .venv/Scripts/activate   # Windows",
        "pip install -e '.[dev]'",
        "cp .env.example .env",
        "python main.py                                    # starts on http://localhost:9380",
    ), sp(0.2)]

    s += [h2("Docker Setup (Recommended for Teams)")]
    s += [code(
        "cd omniai",
        "docker compose up --build",
        "# API at http://localhost:9380",
        "# Frontend at http://localhost:5173",
    ), sp(0.15)]

    s += [h2("Default Admin Credentials")]
    s += [tbl([
        ["Setting",        "Default value"],
        ["Email",          "admin@omniai.local"],
        ["Password",       "Admin12345!"],
        ["Tenant slug",    "local-dev"],
        ["API base URL",   "http://localhost:9380"],
        ["Docs (Swagger)", "http://localhost:9380/docs"],
    ]), sp(0.2)]
    s += [box(
        "<b>Change these immediately</b> before deploying to a server! "
        "Set <tt>BOOTSTRAP_ADMIN_EMAIL</tt>, <tt>BOOTSTRAP_ADMIN_PASSWORD</tt>, "
        "and <tt>AUTH_SECRET</tt> in your <tt>.env</tt> file.",
        bg=ROSE_BG, border=ROSE, label="Security:"
    ), sp(0.25)]

    s += [h2("Project Layout (Backend)")]
    s += [tbl([
        ["Folder",               "What lives here"],
        ["omniai/application/",  "Business logic -- services that do the actual work"],
        ["omniai/domain/",       "Data models -- the 'nouns' of the system (Document, Agent, etc.)"],
        ["omniai/interfaces/",   "HTTP routes -- the URLs your browser or app calls"],
        ["omniai/adapters/",     "Database, object storage, search engine connections"],
        ["omniai/plugins/",      "Swappable components: parsers, LLMs, sandboxes, embeddings"],
        ["omniai/config/",       "All settings -- read from environment variables"],
        ["omniai/security/",     "Encryption, password hashing, RBAC permissions"],
        ["omniai/observability/","Metrics, cost tracking, audit log, tracing"],
        ["tests/",               "Automated tests (340+ passing)"],
    ]), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 2. CORE CONCEPTS
# ══════════════════════════════════════════════════════════════════════════════
def sec_concepts():
    s = [sec_hdr("2.  Core Concepts", VIOLET), sp(0.25)]

    s += [h2("Tenants -- The Top-Level Container")]
    s += [p("Every piece of data in OmniAI belongs to a <b>Tenant</b>. A tenant is like a company "
            "account -- completely isolated from other tenants. When you run OmniAI for yourself, "
            "you have one tenant. If you host it for multiple teams, each team is a separate tenant.")]
    s += [sp(0.1), tbl([
        ["Concept",     "Plain-English meaning"],
        ["Tenant",      "Your organisation's private space -- nobody else can see your data"],
        ["User",        "A person who logs in; belongs to one or more tenants"],
        ["Role",        "OWNER / ADMIN / MEMBER -- controls what a user can do"],
        ["Team",        "A sub-group of users within a tenant (for organising people)"],
        ["API Key",     "A token (starts with omsk_) that lets code talk to OmniAI without logging in"],
    ]), sp(0.25)]

    s += [h2("Collections -- Folders for Your Documents")]
    s += [p("A <b>Collection</b> is a group of related documents -- like a folder. Each collection has "
            "its own AI embedding model (controls how documents are searched) and chunk template "
            "(controls how documents are split up).")]
    s += [p("<b>Example:</b>  You might have a 'Legal Documents' collection and a 'Product Manuals' "
            "collection. They stay separate so searching legal questions only looks in legal docs.")]
    s += [sp(0.1), tbl([
        ["Property",         "What it controls"],
        ["name",             "Human-readable label"],
        ["embedding_model",  "AI model that converts text to numbers (for search)"],
        ["chunk_template",   "How documents are split: general / qa / sentence_window / small_to_big"],
        ["system_prompt",    "Optional instructions given to the AI when chatting about this collection"],
        ["top_k",            "How many chunks to retrieve per query (default: 5)"],
        ["vector_weight",    "0.0 = pure keyword, 1.0 = pure vector, 0.5 = balanced (default)"],
    ]), sp(0.25)]

    s += [h2("Documents -- Your Files")]
    s += [p("A <b>Document</b> is any file you upload -- PDF, Word (.docx), HTML, plain text. "
            "After uploading, it goes through a pipeline:")]
    s += num([
        "<b>PENDING</b> -- Just uploaded, waiting in the queue.",
        "<b>PARSING</b> -- Being read and converted to plain text.",
        "<b>PARSED</b> -- Text extracted successfully.",
        "<b>EMBEDDING</b> -- Text is being turned into search vectors.",
        "<b>INDEXING</b> -- Vectors are being saved to the search engine.",
        "<b>READY</b> -- Fully searchable! Queries will find it.",
        "<b>FAILED</b> -- Something went wrong (check the error_message field).",
    ])
    s += [sp(0.1), box(
        "<b>Track progress:</b>  Call <tt>GET /v1/documents/{id}/status</tt> -- "
        "it returns a percentage (0-100%) and the current stage.",
        bg=MINT_BG, border=TEAL
    ), sp(0.25)]

    s += [h2("Chunks -- The Searchable Pieces")]
    s += [p("When a document is indexed, it is split into small <b>Chunks</b> -- usually a few "
            "hundred words each. The AI searches these chunks, not the whole document. "
            "This is what makes retrieval fast and precise.")]
    s += [tbl([
        ["Template",       "How it splits your document",                        "Best for"],
        ["general",        "Fixed 1024-character blocks with 100-char overlap",  "Most documents"],
        ["qa",             "Q&A pairs (question / answer sections)",             "FAQ documents"],
        ["sentence_window","Sentence-aware with surrounding context window",     "Precise retrieval"],
        ["small_to_big",   "Small detail chunks + larger parent summaries",      "Long reports"],
    ], widths=[3.2*cm, 7.5*cm, 4.8*cm]), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 3. DOCUMENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
def sec_documents():
    s = [sec_hdr("3.  Document Management", TEAL), sp(0.25)]

    s += [h2("Uploading Documents")]
    s += [p("Upload a single file:")]
    s += [code(
        "POST /v1/collections/{collection_id}/documents/upload",
        "Content-Type: multipart/form-data",
        "file=@your_document.pdf",
    )]
    s += [sp(0.1), p("Upload up to <b>20 files at once</b> (batch upload):")]
    s += [code(
        "POST /v1/collections/{collection_id}/documents/bulk-upload",
        "Content-Type: multipart/form-data",
        "files[]=@doc1.pdf&files[]=@doc2.docx",
    )]
    s += [sp(0.1), tbl([
        ["Supported format",  "MIME type"],
        ["PDF",               "application/pdf"],
        ["Word document",     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        ["HTML",              "text/html"],
        ["Plain text",        "text/plain"],
    ]), sp(0.15)]
    s += [box(
        "<b>Max file size:</b>  100 MB per file (change with <tt>UPLOAD_MAX_BYTES</tt> env var). "
        "<b>Max documents per tenant:</b>  10,000 (change with <tt>TENANT_MAX_DOCUMENTS</tt>). "
        "<b>Max total storage:</b>  50 GB (change with <tt>TENANT_MAX_STORAGE_BYTES</tt>).",
        bg=AMBER_BG, border=AMBER
    ), sp(0.25)]

    s += [h2("Checking Document Status")]
    s += [code(
        "GET /v1/documents/{document_id}/status",
        "",
        "// Response:",
        '{ "status": "READY", "progress_pct": 100, "parser_name": "pdf", "page_count": 12 }',
    ), sp(0.25)]

    s += [h2("Bulk Operations -- Do Things to Many Documents at Once")]
    s += [p("Instead of deleting or reindexing documents one by one, use the bulk endpoint:")]
    s += [code(
        "POST /v1/documents/bulk",
        "{",
        '  "document_ids": ["doc_abc", "doc_def", "doc_xyz"],',
        '  "action": "delete"   // options: delete | reindex | set_tags',
        '  "tags": ["finance", "2025"]  // only needed for set_tags',
        "}",
    ), sp(0.15)]
    s += [tbl([
        ["Action",    "What it does"],
        ["delete",    "Permanently removes the documents AND their chunks from search"],
        ["reindex",   "Re-reads and re-indexes the files (useful after changing embedding model)"],
        ["set_tags",  "Attaches labels to all selected documents at once"],
    ]), sp(0.25)]

    s += [h2("Document Tags")]
    s += [p("Tags are labels you attach to documents to help organise and filter them.")]
    s += [code(
        "PUT /v1/documents/{document_id}/tags",
        '{ "tags": ["contract", "2025", "legal"] }',
        "",
        "// Find all documents with a specific tag:",
        "GET /v1/collections/{collection_id}/documents/by-tag/contract",
    ), sp(0.25)]

    s += [h2("Downloading & Reading Document Content")]
    s += [code(
        "GET /v1/documents/{document_id}/raw          // download original file bytes",
        "GET /v1/documents/{document_id}/text         // get the extracted plain text",
        "GET /v1/documents/{document_id}/download-url // get a time-limited download link",
    ), sp(0.25)]

    s += [h2("Knowledge Graph")]
    s += [p("OmniAI automatically extracts <b>entities and relationships</b> from your documents "
            "and builds a knowledge graph. For example, from a legal document it might extract: "
            "<i>Acme Corp -- signed -- Contract 2025-001</i>.")]
    s += [code(
        "GET /v1/documents/{document_id}/graph           // triples in one document",
        "GET /v1/collections/{collection_id}/graph       // all triples in a collection",
        "GET /v1/collections/{collection_id}/graph?entity=Acme Corp  // filter by entity",
    ), sp(0.1)]
    s += [tbl([
        ["Field",       "Meaning"],
        ["subject",     "The main thing being talked about (e.g. 'Acme Corp')"],
        ["predicate",   "The relationship (e.g. 'signed')"],
        ["object",      "What it relates to (e.g. 'Contract 2025-001')"],
        ["confidence",  "How sure the AI is (0.0 - 1.0)"],
    ]), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 4. SEARCH & RETRIEVAL
# ══════════════════════════════════════════════════════════════════════════════
def sec_retrieval():
    s = [sec_hdr("4.  Search & Retrieval", VIOLET), sp(0.25)]

    s += [p("Retrieval is the heart of OmniAI -- it finds the most relevant chunks from your "
            "documents to answer a question. The system uses <b>hybrid search</b> by default: "
            "a combination of keyword search (BM25) and AI vector search.")]
    s += [sp(0.15)]

    s += [h2("Basic Search")]
    s += [code(
        "POST /v1/retrieve",
        "{",
        '  "query": "What are the payment terms?",',
        '  "collection_ids": ["col_abc", "col_def"],   // search multiple collections',
        '  "top_k": 8,                                 // how many results to return',
        '  "vector_weight": 0.7                        // 0=keyword only, 1=vector only',
        "}",
    ), sp(0.1)]
    s += [p("Each result includes:")]
    s += bul([
        "<b>text</b> -- the actual passage found",
        "<b>score</b> -- relevance score (0 to 1, higher is better)",
        "<b>document_id / document_name</b> -- which document it came from",
        "<b>ordinal</b> -- position within the document",
    ])
    s += [sp(0.25)]

    s += [h2("HyDE -- Smarter Search (Hypothetical Document Embeddings)")]
    s += [p("HyDE makes search much better. Instead of searching for your query directly, "
            "the AI first <i>imagines</i> a perfect answer, then searches for chunks that "
            "match that imagined answer. Particularly good for conceptual questions.")]
    s += [code(
        "POST /v1/retrieve",
        '{',
        '  "query": "What causes hyperinflation?",',
        '  "hyde": true,',
        '  "hyde_model": "gpt-4o"    // which model writes the hypothetical answer',
        "}",
    ), sp(0.1)]
    s += [box(
        "<b>If HyDE fails</b> (e.g. no LLM configured), the system silently falls back to "
        "normal search -- you never get an error, just standard results.",
        bg=MINT_BG, border=TEAL
    ), sp(0.25)]

    s += [h2("Streaming Search -- Results Appear Instantly")]
    s += [p("Instead of waiting for all results before showing anything, streaming returns "
            "each result the moment it is found -- one by one, in real time.")]
    s += [code(
        "POST /v1/retrieve/stream",
        '{ "query": "renewable energy trends", "top_k": 10 }',
        "",
        "// Server-Sent Events stream:",
        'data: { "text": "Solar capacity doubled in 2024...", "score": 0.95 }',
        'data: { "text": "Wind installations rose by 30%...", "score": 0.91 }',
        "data: [DONE]",
    ), sp(0.25)]

    s += [h2("Tool Calling -- AI Searches Automatically")]
    s += [p("Give the AI model a special 'tool' so it can search your documents <i>by itself</i> "
            "while answering. The AI decides when to search and what to search for.")]
    s += [code(
        "POST /v1/retrieve/tool",
        '{ "question": "Summarise our Q4 financials", "top_k": 8 }',
        "",
        "// Response includes:",
        '{ "answer": "...", "hits": [...], "tool_calls_made": 2 }',
    ), sp(0.25)]

    s += [h2("Multi-Modal Search (Text + Images)")]
    s += [p("Search using an image instead of text. Send a base64-encoded image and the system "
            "automatically uses the CLIP model to find visually or conceptually similar documents.")]
    s += [code(
        "POST /v1/retrieve",
        '{',
        '  "query": "data:image/jpeg;base64,/9j/4AAQ...",  // base64 image',
        '  "collection_ids": ["col_abc"]',
        "}",
        "",
        "// OmniAI auto-detects 'data:image/' prefix and routes to CLIP model",
    ), sp(0.1)]
    s += [box(
        "<b>Install:</b>  <tt>pip install open-clip-torch torch Pillow</tt>  "
        "to enable multi-modal embeddings.  No config change needed -- the system detects "
        "image inputs automatically.",
        bg=AMBER_BG, border=AMBER
    ), sp(0.25)]

    s += [h2("Reranking -- Better Result Ordering")]
    s += [p("After retrieval, a second AI pass <b>re-orders</b> results to put the most relevant "
            "ones first. Enable via the <tt>RERANKER_KIND</tt> environment variable:")]
    s += [tbl([
        ["RERANKER_KIND",        "How it works",                                  "Requirement"],
        ["paired",               "Embeds (query, chunk) pairs and scores them",   "Nothing extra"],
        ["sentencetransformers", "SentenceTransformers cross-encoder model",      "pip install sentence-transformers"],
    ], widths=[4*cm, 7*cm, 4.5*cm]), sp(0.25)]

    s += [h2("Retrieval Caching")]
    s += [p("Identical queries return cached results instantly instead of re-running the full "
            "vector search. Set the TTL (time-to-live) in seconds:")]
    s += [code(
        "RETRIEVAL_CACHE_TTL_SECONDS=300   # cache results for 5 minutes",
        "# Set to 0 (default) to disable caching",
    ), sp(0.1)]
    s += [p("Submit feedback to improve search quality over time:")]
    s += [code(
        "POST /v1/observability/retrieval-feedback",
        '{ "query_hash": "abc123", "chunk_id": "chunk_xyz", "rank": 1, "relevant": true }',
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 5. CHAT & CONVERSATIONS
# ══════════════════════════════════════════════════════════════════════════════
def sec_chat():
    s = [sec_hdr("5.  Chat & Conversations", OCEAN), sp(0.25)]

    s += [p("Conversations let you have a <b>multi-turn chat</b> with an AI that uses your documents "
            "as its knowledge base. Every AI answer includes <b>citations</b> -- references to the "
            "exact document passages it used.")]
    s += [sp(0.15)]

    s += [h2("Creating & Managing Conversations")]
    s += [code(
        "POST /v1/conversations",
        "{",
        '  "title": "Q4 Financial Analysis",',
        '  "collection_ids": ["col_legal", "col_finance"],  // which docs to search',
        '  "model_provider": "anthropic",',
        '  "model_name": "claude-3-5-sonnet-20241022",',
        '  "system_prompt": "You are a financial analyst. Be concise.",',
        '  "top_k": 6,',
        '  "temperature": 0.3',
        "}",
    ), sp(0.15)]
    s += [tbl([
        ["Operation",   "Endpoint"],
        ["List all",    "GET /v1/conversations"],
        ["Get one",     "GET /v1/conversations/{id}"],
        ["Update",      "PATCH /v1/conversations/{id}  (title, pinned, model, system_prompt)"],
        ["Delete",      "DELETE /v1/conversations/{id}"],
        ["List messages","GET /v1/conversations/{id}/messages"],
    ]), sp(0.25)]

    s += [h2("Sending a Message (with RAG)")]
    s += [p("When you send a message, OmniAI automatically:")]
    s += num([
        "Searches your linked collections for relevant chunks.",
        "Passes those chunks as context to the AI model.",
        "Streams the AI's response back to you in real time.",
        "Records citations (which chunks were used and their scores).",
    ])
    s += [sp(0.1), code(
        "POST /v1/chat",
        "{",
        '  "conversation_id": "conv_abc123",',
        '  "content": "What were the main risks identified in the Q4 report?"',
        "}",
        "",
        "// Response is streamed (text/event-stream):",
        'data: {"delta": "The main risks identified were..."}',
        'data: {"delta": " supply chain disruptions and..."}',
        'data: {"citations": [{"document_name": "Q4_Report.pdf", "text": "..."}]}',
        "data: [DONE]",
    ), sp(0.25)]

    s += [h2("Regenerate a Response")]
    s += [p("Didn't like the answer? Ask the AI to try again, optionally with different settings:")]
    s += [code(
        "POST /v1/chat/regenerate",
        "{",
        '  "conversation_id": "conv_abc123",',
        '  "temperature": 0.8,',
        '  "model_name": "gpt-4o"   // try a different model',
        "}",
    ), sp(0.25)]

    s += [h2("Forking -- Branch a Conversation")]
    s += [p("Create a copy of a conversation at any point and explore a different direction "
            "without losing your original chat. Like a 'Save Game' checkpoint.")]
    s += [code(
        "POST /v1/conversations/{id}/fork",
        "{",
        '  "title": "Alternative analysis",',
        '  "fork_at_message_id": "msg_abc123"   // optional: fork from a specific message',
        "}",
    ), sp(0.25)]

    s += [h2("Exporting Conversations")]
    s += [p("Download any conversation as a file you can read in any text editor or word processor:")]
    s += [code(
        "GET /v1/conversations/{id}/export?format=markdown   // nice formatted text",
        "GET /v1/conversations/{id}/export?format=json       // raw data for developers",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 6. LLM PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════
def sec_providers():
    s = [sec_hdr("6.  LLM Providers", AMBER), sp(0.25)]

    s += [p("OmniAI supports multiple AI model providers. You register them once with your API key "
            "and then any conversation or agent can use them. All credentials are encrypted at rest.")]
    s += [sp(0.15)]

    s += [h2("Adding a Provider")]
    s += [code(
        "POST /v1/providers",
        "{",
        '  "kind": "anthropic",   // anthropic | openai | gemini | ollama',
        '  "name": "My Claude",',
        '  "credentials": { "api_key": "sk-ant-..." },',
        '  "default_model": "claude-3-5-sonnet-20241022"',
        "}",
    ), sp(0.15)]
    s += [tbl([
        ["Provider",   "kind=",      "Popular models"],
        ["Anthropic",  "anthropic",  "claude-3-5-sonnet-20241022, claude-3-opus-20240229"],
        ["OpenAI",     "openai",     "gpt-4o, gpt-4o-mini, gpt-3.5-turbo"],
        ["Google",     "gemini",     "gemini-1.5-pro, gemini-1.5-flash"],
        ["Ollama",     "ollama",     "llama3.2, mistral, phi3 (runs on your machine)"],
    ], widths=[2.8*cm, 2.7*cm, 10*cm]), sp(0.25)]

    s += [h2("Ollama -- Run AI Models Locally (Free)")]
    s += [p("Ollama lets you run AI models on your own computer for free -- no API key needed. "
            "Great for privacy-sensitive workflows.")]
    s += [code(
        "# 1. Install Ollama from https://ollama.com",
        "# 2. Pull a model:",
        "ollama pull llama3.2",
        "",
        "# 3. Register it in OmniAI:",
        "POST /v1/providers",
        '{ "kind": "ollama", "name": "Local LLaMA", "base_url": "http://localhost:11434" }',
    ), sp(0.15)]
    s += [box(
        "<b>For embedding + OCR:</b>  Ollama also provides embedding models "
        "(<tt>nomic-embed-text</tt>) and vision models (<tt>llava</tt>) that OmniAI uses "
        "for indexing and OCR respectively.",
        bg=MINT_BG, border=TEAL
    ), sp(0.25)]

    s += [h2("Listing Available Models")]
    s += [code(
        "GET /v1/providers/{provider_id}/models",
        "",
        "// Returns list of model names the provider supports",
    ), sp(0.25)]

    s += [h2("Managing Providers")]
    s += [code(
        "GET    /v1/providers              // list all registered providers",
        "PATCH  /v1/providers/{id}         // update credentials or default model",
        "DELETE /v1/providers/{id}         // remove provider",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 7. AGENT PLATFORM
# ══════════════════════════════════════════════════════════════════════════════
def sec_agents():
    s = [sec_hdr("7.  Agent Platform", ROSE), sp(0.25)]

    s += [p("An <b>Agent</b> is an automated AI workflow. You design it as a graph (diagram) of "
            "steps -- called <b>nodes</b> -- connected by arrows. When you run the agent, it "
            "follows the graph, executing each node in order.")]
    s += [sp(0.1), box(
        "<b>Think of it like a recipe:</b>  Node 1 = search documents. Node 2 = run a calculation. "
        "Node 3 = ask a human to approve. Node 4 = write the final answer. "
        "The agent follows every step automatically.",
        bg=ROSE_BG, border=ROSE
    ), sp(0.25)]

    s += [h2("Creating an Agent")]
    s += [code(
        "POST /v1/agents",
        "{",
        '  "name": "Contract Analyser",',
        '  "description": "Searches legal docs and summarises key clauses",',
        '  "definition": {',
        '    "nodes": [',
        '      { "id": "retrieve", "type": "retrieval",',
        '        "collection_id": "col_legal", "top_k": 6 },',
        '      { "id": "generate", "type": "llm",',
        '        "prompt": "Summarise the key clauses: {{context}}" }',
        '    ],',
        '    "edges": [',
        '      { "from": "retrieve", "to": "generate" }',
        '    ]',
        '  }',
        "}",
    ), sp(0.25)]

    s += [h2("Node Types")]
    s += [tbl([
        ["Node type",    "What it does"],
        ["retrieval",    "Searches a collection and adds results to context"],
        ["llm",          "Calls an AI model with a prompt (uses {{context}} and {{user_input}})"],
        ["code",         "Runs Python, JavaScript, or Bash code (requires sandbox enabled)"],
        ["human_input",  "Pauses the run and waits for a human to approve or provide input"],
        ["fan_out",      "Splits into multiple parallel branches (for doing things simultaneously)"],
        ["join",         "Waits for all parallel branches to finish, then merges their results"],
    ]), sp(0.25)]

    s += [h2("Running an Agent")]
    s += [code(
        "POST /v1/agents/{agent_id}/runs",
        '{ "input": "Analyse the Acme Corp contract for payment risks" }',
        "",
        "GET /v1/agents/{agent_id}/runs/{run_id}   // check status",
        "",
        "// Status values: QUEUED -> RUNNING -> COMPLETED (or FAILED, PAUSED, CANCELLED)",
    ), sp(0.25)]

    s += [h2("Parallel Fan-Out / Join -- Do Multiple Things at Once")]
    s += [p("Add a <b>fan_out</b> node to split the workflow into parallel branches that run "
            "simultaneously, then a <b>join</b> node to merge all their results.")]
    s += [code(
        '"nodes": [',
        '  { "id": "fanout", "type": "fan_out" },',
        '  { "id": "search_legal",   "type": "retrieval", "collection_id": "col_legal" },',
        '  { "id": "search_finance", "type": "retrieval", "collection_id": "col_finance" },',
        '  { "id": "join",    "type": "join" },',
        '  { "id": "answer",  "type": "llm", "prompt": "Summarise: {{context}}" }',
        "],",
        '"edges": [',
        '  { "from": "fanout",        "to": "search_legal" },',
        '  { "from": "fanout",        "to": "search_finance" },',
        '  { "from": "search_legal",  "to": "join" },',
        '  { "from": "search_finance","to": "join" },',
        '  { "from": "join",          "to": "answer" }',
        "]",
    ), sp(0.1)]
    s += [box(
        "<b>Result:</b>  Both searches run at the same time. When both finish, 'join' combines "
        "all found chunks and passes them to 'answer'. Twice as fast as running sequentially!",
        bg=AMBER_BG, border=AMBER
    ), sp(0.25)]

    s += [h2("Human-in-the-Loop (HITL) -- Pause & Approve")]
    s += [p("Add a <b>human_input</b> node anywhere in your graph. When the agent reaches it, "
            "the run <b>pauses</b> and waits for a human to review and approve before continuing.")]
    s += num([
        "Agent reaches the <tt>human_input</tt> node.",
        "Run status changes to <b>PAUSED</b>.",
        "Your system polls the run status and shows it to a human reviewer.",
        "Human calls the <b>resume</b> endpoint with their feedback.",
        "Agent continues from the next node automatically.",
    ])
    s += [sp(0.1), code(
        "POST /v1/agents/{agent_id}/runs/{run_id}/resume",
        "{",
        '  "human_input": "Approved. The payment terms look correct.",',
        '  "approved": true',
        "}",
    ), sp(0.25)]

    s += [h2("Time-Travel Replay -- Undo & Retry Any Step")]
    s += [p("Every agent run records a full <b>event log</b> -- every step is saved. You can "
            "'rewind' to any past event and replay the run from that point, optionally with a "
            "different input. Creates a new run, preserving the original.")]
    s += [code(
        "POST /v1/agents/{agent_id}/runs/{run_id}/replay",
        "{",
        '  "from_event": 3,                           // replay from event index 3',
        '  "input_override": "Try a different approach"  // optional new input',
        "}",
        "",
        "// Returns a new run_id. The new run fast-forwards through events 0-2,",
        "// then continues LIVE from event 3.",
    ), sp(0.25)]

    s += [h2("Agent Template Marketplace")]
    s += [p("Ready-made agent blueprints you can import with one API call. No need to build "
            "from scratch -- pick a template and customise it.")]
    s += [code(
        "GET /v1/marketplace/templates                 // browse available templates",
        "GET /v1/marketplace/templates/{template_id}  // see full definition",
        "",
        "POST /v1/agents/import-template",
        '{ "template_id": "parallel-research", "name": "My Research Agent" }',
    ), sp(0.1)]
    s += [tbl([
        ["Template ID",       "What it does"],
        ["basic-rag",         "Search a collection, then generate an answer. Simplest setup."],
        ["parallel-research", "Search TWO collections simultaneously, then combine and answer."],
        ["human-review",      "Search, generate draft answer, pause for human approval, then send."],
        ["code-executor",     "Search context, then run a Python script with the results."],
        ["summarisation",     "Retrieve 10 passages from a document and write a full summary."],
    ]), sp(0.15)]
    s += [p("<b>Import from your own URL</b> (share templates with your team):")]
    s += [code(
        'POST /v1/agents/import-template',
        '{ "url": "https://your-server.com/my-template.json" }',
    ), sp(0.25)]

    s += [h2("Multi-Language Code Nodes")]
    s += [p("Code nodes can run <b>Python, JavaScript, or Bash</b>. The agent automatically "
            "injects the user's question and retrieved context as variables.")]
    s += [tbl([
        ["Language",    "Variables injected",          "Example use case"],
        ["python",      "user_input, context_text",    "Data analysis, calculations, file processing"],
        ["javascript",  "user_input, context_text",    "JSON manipulation, web logic"],
        ["bash",        "$USER_INPUT, $CONTEXT_TEXT",  "Shell commands, file operations, system tasks"],
    ], widths=[2.8*cm, 5.2*cm, 7.5*cm]), sp(0.15)]
    s += [code(
        "// JavaScript code node example:",
        "const words = context_text.split(' ').length;",
        "console.log(`Context has ${words} words.`);",
    ), sp(0.25)]

    s += [h2("Sandbox -- Safe Code Execution")]
    s += [p("Code nodes run inside a <b>sandbox</b> -- an isolated container that prevents "
            "malicious code from accessing your server, files, or secrets.")]
    s += [tbl([
        ["SANDBOX_KIND", "Safety level",                      "Requirement"],
        ["none",         "Code nodes are disabled",           "Nothing -- safest option if you do not need code"],
        ["subprocess",   "Runs in a separate Python process", "Nothing extra"],
        ["docker",       "Docker container isolation",        "Docker installed"],
        ["gvisor",       "Intercepts all system calls (best)", "gVisor runsc binary installed"],
    ], widths=[3*cm, 6.5*cm, 6*cm]), sp(0.1)]
    s += [code("SANDBOX_KIND=gvisor", "GVISOR_RUNSC_BIN=/usr/local/bin/runsc"), sp(0.1)]
    s += [box(
        "<b>gVisor not installed?</b>  If the <tt>runsc</tt> binary is not found, OmniAI "
        "automatically falls back to <tt>subprocess</tt> mode with a log warning. "
        "Your agents still run -- just with less isolation.",
        bg=MINT_BG, border=TEAL
    ), sp(0.25)]

    s += [h2("Run Cost Tracking & Alerting")]
    s += [p("Every agent run shows how much it cost (estimated USD based on tokens used). "
            "Set a threshold -- if any run exceeds it, a warning appears in the logs.")]
    s += [code(
        "AGENT_RUN_COST_ALERT_USD=0.10   # warn if a run costs more than $0.10",
        "",
        "GET /v1/agents/{id}/runs/{run_id}",
        '// Response includes: { "cost_usd": 0.0042, "status": "COMPLETED" }',
    ), sp(0.25)]

    s += [h2("Exporting Agent Runs")]
    s += [p("Download a full record of what the agent did -- every step, every result:")]
    s += [code(
        "GET /v1/agents/{id}/runs/{run_id}/export?format=json      // full event log",
        "GET /v1/agents/{id}/runs/{run_id}/export?format=markdown  // readable summary",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 8. DEPLOYMENTS
# ══════════════════════════════════════════════════════════════════════════════
def sec_deployments():
    s = [sec_hdr("8.  Deployments -- Share AI with the World", OCEAN), sp(0.25)]

    s += [p("A <b>Deployment</b> lets you publish a collection or agent as a public-facing "
            "chat page or webhook endpoint -- without requiring users to log in. "
            "Perfect for customer support bots, internal knowledge bases, or public Q&A pages.")]
    s += [sp(0.15)]

    s += [h2("Creating a Deployment")]
    s += [code(
        "POST /v1/deployments",
        "{",
        '  "name": "Customer Support Bot",',
        '  "slug": "support",                  // your URL: /c/support',
        '  "kind": "public_chat",              // public_chat | webhook',
        '  "target_kind": "collection",        // collection | agent',
        '  "target_id": "col_support_docs",',
        '  "anonymous_allowed": true,          // no login required',
        '  "model_provider": "openai",',
        '  "model_name": "gpt-4o-mini",',
        '  "system_prompt": "You are a helpful customer support agent.",',
        '  "rate_limit_per_minute": 20,        // per visitor',
        '  "daily_message_quota": 500          // max messages per day',
        "}",
    ), sp(0.25)]

    s += [h2("Accessing the Public Chat Page")]
    s += [code(
        "// Anyone (no login needed) can chat at:",
        "GET  /c/{slug}            // loads the chat interface",
        "POST /c/{slug}/chat       // send a message",
        '{ "content": "What is your return policy?" }',
    ), sp(0.25)]

    s += [h2("Rate Limits & Quotas")]
    s += [tbl([
        ["Setting",              "What it controls"],
        ["rate_limit_per_minute","Max messages per visitor per minute (default: 20)"],
        ["daily_message_quota",  "Max total messages across ALL visitors per day (default: 500)"],
        ["anonymous_allowed",    "If false, visitors must log in before chatting"],
    ]), sp(0.15)]
    s += [box(
        "<b>When a quota is exceeded:</b>  The API returns HTTP 429 (Too Many Requests) with "
        "a <tt>Retry-After</tt> header telling the client when to try again.",
        bg=AMBER_BG, border=AMBER
    ), sp(0.25)]

    s += [h2("Managing Deployments")]
    s += [code(
        "GET    /v1/deployments          // list all your deployments",
        "GET    /v1/deployments/{id}     // get status (message counts, today's usage)",
        "PATCH  /v1/deployments/{id}     // update model, quota, system prompt, etc.",
        "DELETE /v1/deployments/{id}     // take it offline",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 9. CONNECTORS
# ══════════════════════════════════════════════════════════════════════════════
def sec_connectors():
    s = [sec_hdr("9.  Connectors -- Sync External Data Sources", FOREST), sp(0.25)]

    s += [p("Connectors automatically pull content from external platforms into your OmniAI "
            "collections. Once set up, they run on a schedule -- your knowledge base stays "
            "up to date without any manual uploads.")]
    s += [sp(0.15)]

    s += [h2("Available Connectors")]
    s += [tbl([
        ["kind",           "Source",            "What gets synced"],
        ["local_folder",   "Local folder",      "All files in a directory on the server"],
        ["s3",             "Amazon S3",         "Objects in an S3 bucket / prefix"],
        ["gdrive",         "Google Drive",      "Docs, Sheets, Slides, PDFs in a folder"],
        ["sharepoint",     "SharePoint Online", "Documents in a SharePoint library"],
        ["notion",         "Notion",            "Pages in a Notion workspace or database"],
        ["confluence",     "Confluence",        "Pages in a Confluence space"],
        ["slack",          "Slack",             "Messages and files from channels"],
    ], widths=[2.8*cm, 3.5*cm, 9.2*cm]), sp(0.25)]

    s += [h2("Creating a Connector")]
    s += [code(
        "POST /v1/connectors",
        "{",
        '  "name": "Legal Drive",',
        '  "kind": "gdrive",',
        '  "collection_id": "col_legal",',
        '  "sync_interval_seconds": 3600,   // sync every hour',
        '  "config": {',
        '    "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"',
        '  }',
        "}",
    ), sp(0.1)]
    s += [box(
        "<b>Deduplication:</b>  Connectors track the SHA-256 hash of every file they sync. "
        "If a file has not changed since the last sync, it is skipped automatically -- "
        "no duplicate documents.",
        bg=MINT_BG, border=TEAL
    ), sp(0.25)]

    s += [h2("Connector Credentials (Environment Variables)")]
    s += [tbl([
        ["Connector",   "Required environment variable(s)"],
        ["gdrive",      "GDRIVE_SERVICE_ACCOUNT_JSON (path to service account key file)"],
        ["sharepoint",  "SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET"],
        ["notion",      "NOTION_API_KEY"],
        ["confluence",  "CONFLUENCE_BASE_URL, CONFLUENCE_API_TOKEN"],
        ["slack",       "SLACK_BOT_TOKEN"],
        ["s3",          "OBJECT_STORE_ACCESS_KEY, OBJECT_STORE_SECRET_KEY, OBJECT_STORE_ENDPOINT"],
    ], widths=[3*cm, 12.5*cm]), sp(0.25)]

    s += [h2("Triggering a Sync")]
    s += [code(
        "POST /v1/connectors/{id}/sync   // run sync immediately (don't wait for schedule)",
        "",
        "// Response:",
        '{ "discovered": 45, "ingested": 12, "skipped_duplicate": 33, "errors": 0 }',
    ), sp(0.25)]

    s += [h2("Preview Before Syncing")]
    s += [code(
        "GET /v1/connectors/preview?connector_id={id}",
        "",
        "// Returns up to 20 items that WOULD be ingested -- without actually doing it",
        "// Great for verifying connector config before running for real",
    ), sp(0.25)]

    s += [h2("Managing Connectors")]
    s += [code(
        "GET    /v1/connectors        // list all connectors",
        "GET    /v1/connectors/{id}   // get status (last_sync_at, last_synced_count, last_error)",
        "PATCH  /v1/connectors/{id}   // update config, sync_interval, or enabled flag",
        "DELETE /v1/connectors/{id}   // remove connector (does NOT delete synced documents)",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 10. IDENTITY & ACCESS
# ══════════════════════════════════════════════════════════════════════════════
def sec_identity():
    s = [sec_hdr("10.  Identity & Access", INDIGO), sp(0.25)]

    s += [h2("Registration & Login")]
    s += [code(
        "POST /v1/auth/register",
        '{ "email": "alice@example.com", "password": "MyStr0ng!Pass", "display_name": "Alice" }',
        "",
        "POST /v1/auth/login",
        '{ "email": "alice@example.com", "password": "MyStr0ng!Pass" }',
        "",
        "// Response: { 'token': 'eyJ...', 'mfa_required': false }",
        "// Use: Authorization: Bearer eyJ...  on all future requests",
    ), sp(0.15)]
    s += [box(
        "<b>Account lockout:</b>  After 5 failed logins, the account is locked for 15 minutes. "
        "Configure with <tt>LOGIN_LOCKOUT_THRESHOLD</tt> and <tt>LOGIN_LOCKOUT_MINUTES</tt>.",
        bg=ROSE_BG, border=ROSE, label="Security:"
    ), sp(0.25)]

    s += [h2("Password Reset")]
    s += [code(
        "POST /v1/auth/request-password-reset",
        '{ "email": "alice@example.com" }',
        "",
        "// In dev mode the response includes the token directly.",
        "// In production: send the token to the user by email.",
        "",
        "POST /v1/auth/reset-password",
        '{ "token": "abc123xyz", "new_password": "NewStr0ng!Pass2" }',
    ), sp(0.25)]

    s += [h2("API Keys -- Code Access Without Passwords")]
    s += [p("For scripts and integrations, create an API key. It starts with <tt>omsk_</tt> "
            "and is sent in the <tt>Authorization: Bearer omsk_...</tt> header.")]
    s += [code(
        "POST /v1/api-keys",
        '{ "name": "CI Pipeline", "scopes": ["read", "write"] }',
        "",
        "// Response: { 'key': 'omsk_live_abc123...', 'id': 'key_xyz' }",
        "// IMPORTANT: Copy the key now -- it won't be shown again!",
        "",
        "POST /v1/api-keys/{id}/revoke   // deactivate key",
    ), sp(0.25)]

    s += [h2("Multi-Factor Authentication (MFA / TOTP)")]
    s += [p("Enable TOTP-based two-factor authentication. Works with any authenticator app "
            "(Google Authenticator, Authy, 1Password, etc.).")]
    s += num([
        "Call <tt>POST /v1/auth/mfa/setup</tt> -- get a QR code URI.",
        "Scan the QR code with your authenticator app.",
        "Call <tt>POST /v1/auth/mfa/confirm</tt> with the 6-digit code to enable.",
        "On future logins, the login response includes <tt>mfa_required: true</tt>.",
        "Call <tt>POST /v1/auth/mfa/verify</tt> with the current 6-digit code to complete login.",
    ])
    s += [sp(0.1), code(
        "POST /v1/auth/mfa/setup          // { 'totp_uri': 'otpauth://...' }",
        "POST /v1/auth/mfa/confirm  { 'code': '123456' }",
        "POST /v1/auth/mfa/verify   { 'code': '654321' }",
        "POST /v1/auth/mfa/disable  { 'code': '123456' }  // to turn off",
    ), sp(0.25)]

    s += [h2("OIDC -- Login with Google, GitHub, or Microsoft")]
    s += [p("Let users sign in with their existing Google, GitHub, or Microsoft account -- "
            "no password required.")]
    s += [tbl([
        ["Provider",   "env vars needed"],
        ["Google",     "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"],
        ["GitHub",     "GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET"],
        ["Microsoft",  "MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET"],
    ]), sp(0.15)]
    s += [code(
        "GET /v1/auth/oidc/{provider}/login       // redirect user here",
        "GET /v1/auth/oidc/{provider}/callback    // OAuth2 callback (set in provider dashboard)",
    ), sp(0.25)]

    s += [h2("Teams & Roles")]
    s += [code(
        "POST /v1/teams   { 'name': 'Legal Team', 'description': '...' }",
        "GET  /v1/teams    // list teams",
        "",
        "// Tenant roles: OWNER (full control) | ADMIN (manage users) | MEMBER (use features)",
    ), sp(0.25)]

    s += [h2("Inviting Users")]
    s += [p("Instead of sharing passwords, send email invitations. Each invitation expires after "
            "72 hours (configurable).")]
    s += [code(
        "POST /v1/auth/invite",
        '{ "email": "bob@example.com", "role": "MEMBER" }',
        "",
        "// Bob receives an email with a link. When he clicks it, his account is created",
        "// and he is automatically added to your tenant.",
    ), sp(0.25)]

    s += [h2("Per-Collection Access Control (RBAC)")]
    s += [p("Restrict who can read or write specific collections -- even within the same tenant.")]
    s += [code(
        "POST /v1/collections/{id}/members",
        '{ "user_id": "user_bob", "role": "VIEWER" }   // OWNER | EDITOR | VIEWER',
        "",
        "GET /v1/collections/{id}/members   // list who has access",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 11. OBSERVABILITY
# ══════════════════════════════════════════════════════════════════════════════
def sec_observability():
    s = [sec_hdr("11.  Observability", TEAL), sp(0.25)]

    s += [h2("LLM Cost Dashboard")]
    s += [p("Track exactly how much you are spending on AI calls -- broken down by model and time period.")]
    s += [code(
        "GET /v1/observability/cost?days=30",
        "",
        "// Response:",
        "{ 'total_usd': 4.23, 'by_model': { 'gpt-4o': 3.10, 'claude-3-5-sonnet': 1.13 },",
        "  'by_day': [ {'date': '2025-04-01', 'usd': 0.42}, ... ] }",
    ), sp(0.15)]
    s += [box(
        "<b>Cost calculation:</b>  Prompt tokens: $0.002 / 1K.  Completion tokens: $0.006 / 1K. "
        "Adjust with <tt>LLM_COST_PER_1K_PROMPT</tt> and <tt>LLM_COST_PER_1K_COMPLETION</tt> "
        "env vars to match your actual provider rates.",
        bg=AMBER_BG, border=AMBER
    ), sp(0.25)]

    s += [h2("Retrieval Quality Metrics")]
    s += [code(
        "GET /v1/observability/quality",
        "",
        "// Response: { 'ndcg_at_10': 0.72, 'hit_rate': 0.88, 'feedback_count': 142 }",
        "",
        "// Submit feedback (thumbs up/down) to improve the score:",
        "POST /v1/observability/retrieval-feedback",
        '{ "query_hash": "abc123", "chunk_id": "chunk_xyz", "rank": 1, "relevant": true }',
    ), sp(0.15)]
    s += [tbl([
        ["Metric",      "What it means",                          "Good value"],
        ["NDCG@10",     "Normalised Discounted Cumulative Gain -- measures ranking quality", "> 0.7"],
        ["Hit rate",    "Fraction of queries where a relevant chunk appears in top-10",     "> 0.85"],
    ], widths=[2.5*cm, 9.5*cm, 3.5*cm]), sp(0.25)]

    s += [h2("Audit Log")]
    s += [p("Every significant action (login, document delete, agent run, settings change) is "
            "recorded in an audit log. Only admins can view it.")]
    s += [code(
        "GET /v1/admin/audit-events?limit=50&offset=0",
        "",
        "// Each event: { 'action': 'document.delete', 'actor': 'alice@...', ",
        "//               'target_type': 'Document', 'target_id': 'doc_xyz', ",
        "//               'created_at': '2025-04-15T10:22:00Z' }",
    ), sp(0.25)]

    s += [h2("Prometheus Metrics")]
    s += [p("OmniAI exposes a <tt>/v1/metrics</tt> endpoint in Prometheus format. "
            "Plug it into Grafana for real-time dashboards.")]
    s += [code(
        "GET /v1/metrics",
        "",
        "# omniai_http_requests_total{method='POST',path='/v1/chat',status='200'} 1482",
        "# omniai_http_request_duration_seconds_bucket{le='0.5'} 1305",
        "# omniai_rate_limited_total{tenant='...'} 12",
    ), sp(0.25)]

    s += [h2("OpenTelemetry Distributed Tracing")]
    s += [p("Send traces to any OpenTelemetry-compatible backend (Jaeger, Honeycomb, Datadog, etc.):")]
    s += [code(
        "OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317",
        "OTEL_SERVICE_NAME=omniai-api",
    ), sp(0.25)]

    s += [h2("Sentry Error Tracking")]
    s += [code(
        "SENTRY_DSN=https://your-key@sentry.io/your-project",
        "SENTRY_TRACES_SAMPLE_RATE=0.1   # capture 10% of traces",
    ), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 12. SECURITY
# ══════════════════════════════════════════════════════════════════════════════
def sec_security():
    s = [sec_hdr("12.  Security", ROSE), sp(0.25)]

    s += [h2("Rate Limiting")]
    s += [p("Every API endpoint is protected by a token-bucket rate limiter. "
            "If a client sends too many requests, it gets an HTTP 429 response.")]
    s += [code(
        "RATE_LIMIT_PER_MINUTE=120   # max requests per minute per key/IP (default: 120)",
        "",
        "# Exempt paths: /v1/health, /v1/metrics (monitoring never gets locked out)",
    ), sp(0.25)]

    s += [h2("Account Lockout")]
    s += [code(
        "LOGIN_LOCKOUT_THRESHOLD=5    # failed attempts before lockout (default: 5)",
        "LOGIN_LOCKOUT_MINUTES=15     # how long to lock the account (default: 15)",
    ), sp(0.25)]

    s += [h2("Security HTTP Headers")]
    s += [p("All responses include hardened security headers automatically:")]
    s += [tbl([
        ["Header",                   "What it does"],
        ["X-Content-Type-Options",   "Prevents MIME-type sniffing attacks"],
        ["X-Frame-Options: DENY",    "Blocks clickjacking (your page cannot be embedded in iframes)"],
        ["Content-Security-Policy",  "Restricts which scripts and resources can run on the page"],
        ["Referrer-Policy",          "Limits what URL info is sent to third parties"],
        ["Strict-Transport-Security","Forces HTTPS in production (HSTS, 1-year max-age)"],
    ], widths=[5.5*cm, 10*cm]), sp(0.25)]

    s += [h2("Encryption at Rest")]
    s += [p("All sensitive data (LLM provider API keys, connector credentials) is encrypted "
            "before being stored in the database, using AES-256 (Fernet symmetric encryption).")]
    s += [code(
        "ENCRYPTION_KEY=your-32-byte-base64-key-here",
        "# Generate a secure key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'",
    ), sp(0.25)]

    s += [h2("Environment Security Checklist")]
    s += bul([
        "Change <tt>AUTH_SECRET</tt> from the default (used for session tokens).",
        "Change <tt>ENCRYPTION_KEY</tt> from the default (used for stored credentials).",
        "Change admin email and password from defaults.",
        "Set <tt>REGISTRATION_OPEN=false</tt> in production if you do not want public sign-ups.",
        "Use HTTPS (TLS) in front of OmniAI in production.",
        "Never commit your <tt>.env</tt> file to version control.",
    ])
    s += [sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 13. CONFIGURATION REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
def sec_config():
    s = [sec_hdr("13.  Configuration Reference", SLATE), sp(0.25)]
    s += [p("All settings are read from environment variables (or a <tt>.env</tt> file in the "
            "backend directory). Values shown are the defaults.")]
    s += [sp(0.15)]

    def cfg_tbl(rows):
        t = Table(rows, colWidths=[5.8*cm, 4*cm, 5.7*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  DARK),
            ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,0),  8),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LIGHT_BG]),
            ("FONTNAME",      (0,1),(-1,-1), "Courier"),
            ("FONTSIZE",      (0,1),(-1,-1), 7.5),
            ("TEXTCOLOR",     (0,1),(-1,-1), SLATE),
            ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#CBD5E1")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ]))
        return t

    s += [h2("Application")]
    s += [cfg_tbl([
        ["Variable",              "Default",                    "Notes"],
        ["APP_NAME",              "Omni-AI",                    "Name shown in UI and docs"],
        ["APP_ENV",               "development",                "Set 'production' to enable HSTS etc."],
        ["HTTP_PORT",             "9380",                       "Port the API server listens on"],
        ["API_CORS_ORIGINS",      "http://localhost:5173",      "Comma-separated allowed origins"],
        ["REGISTRATION_OPEN",     "true",                       "false = no public sign-up"],
    ]), sp(0.2)]

    s += [h2("Database & Storage")]
    s += [cfg_tbl([
        ["Variable",                   "Default",                             "Notes"],
        ["DB_URL",                     "sqlite:///./omniai-dev.db",           "PostgreSQL in prod"],
        ["AUTO_CREATE_SCHEMA",         "true",                                "Run migrations on start"],
        ["OBJECT_STORE_KIND",          "local",                               "local | s3"],
        ["OBJECT_STORE_LOCAL_DIR",     "./.omniai-storage",                   "Where files are saved"],
        ["OBJECT_STORE_BUCKET",        "omniai",                              "S3 bucket name"],
        ["UPLOAD_MAX_BYTES",           "104857600",                           "100 MB per file"],
        ["TENANT_MAX_DOCUMENTS",       "10000",                               "Per-tenant doc limit"],
        ["TENANT_MAX_STORAGE_BYTES",   "53687091200",                         "50 GB per tenant"],
    ]), sp(0.2)]

    s += [h2("Search & Retrieval")]
    s += [cfg_tbl([
        ["Variable",                   "Default",                "Notes"],
        ["SEARCH_KIND",                "memory",                 "memory|pgvector|pinecone|weaviate"],
        ["PGVECTOR_TABLE",             "omniai_vectors",         "PostgreSQL table name"],
        ["PINECONE_API_KEY",           "(none)",                 "Pinecone cloud key"],
        ["PINECONE_ENVIRONMENT",       "us-east-1-aws",          "Pinecone region"],
        ["WEAVIATE_URL",               "http://localhost:8080",  "Weaviate server URL"],
        ["WEAVIATE_API_KEY",           "(none)",                 "Weaviate auth (optional)"],
        ["RETRIEVAL_CACHE_TTL_SECONDS","0",                      "0 = disabled"],
        ["RERANKER_KIND",              "(none)",                 "paired|sentencetransformers"],
    ]), sp(0.2)]

    s += [h2("LLM & OCR")]
    s += [cfg_tbl([
        ["Variable",              "Default",                   "Notes"],
        ["OLLAMA_BASE_URL",       "http://localhost:11434",    "Ollama server address"],
        ["OCR_KIND",              "none",                      "none|tesseract|ollama_vision"],
        ["OCR_MIN_CHARS_PER_PAGE","50",                        "Pages with fewer chars get OCR'd"],
        ["OCR_IMAGE_DPI",         "200",                       "DPI for image extraction"],
        ["OLLAMA_VISION_MODEL",   "llava",                     "Model used for OCR"],
    ]), sp(0.2)]

    s += [h2("Authentication & Sessions")]
    s += [cfg_tbl([
        ["Variable",               "Default",          "Notes"],
        ["AUTH_SECRET",            "change-me-...",    "MUST change in production"],
        ["ENCRYPTION_KEY",         "dev-only-...",     "MUST change in production"],
        ["SESSION_TTL_MINUTES",    "480",              "8-hour sessions"],
        ["SESSION_COOKIE_NAME",    "omniai_session",   "Cookie name for browser sessions"],
        ["LOGIN_LOCKOUT_THRESHOLD","5",                "Failed logins before lockout"],
        ["LOGIN_LOCKOUT_MINUTES",  "15",               "Lockout duration"],
        ["INVITATION_EXPIRY_HOURS","72",               "Invitation link lifetime"],
    ]), sp(0.2)]

    s += [h2("Agent Platform")]
    s += [cfg_tbl([
        ["Variable",                  "Default",                              "Notes"],
        ["SANDBOX_KIND",              "none",                                 "none|subprocess|docker|gvisor"],
        ["SANDBOX_DEFAULT_TIMEOUT",   "30.0",                                 "Seconds before code is killed"],
        ["GVISOR_RUNSC_BIN",          "runsc",                                "Path to gVisor binary"],
        ["AGENT_RUN_COST_ALERT_USD",  "0.0",                                  "0 = disabled"],
        ["AGENT_MARKETPLACE_URL",     "https://marketplace.omniai.dev/...",   "Custom template registry"],
    ]), sp(0.2)]

    s += [h2("Observability")]
    s += [cfg_tbl([
        ["Variable",                     "Default",    "Notes"],
        ["OTEL_EXPORTER_OTLP_ENDPOINT",  "(none)",     "OpenTelemetry collector URL"],
        ["OTEL_SERVICE_NAME",            "omniai-api", "Service name in traces"],
        ["SENTRY_DSN",                   "(none)",     "Sentry project DSN"],
        ["SENTRY_TRACES_SAMPLE_RATE",    "0.1",        "Fraction of traces sent"],
        ["LLM_COST_PER_1K_PROMPT",       "0.002",      "USD per 1K prompt tokens"],
        ["LLM_COST_PER_1K_COMPLETION",   "0.006",      "USD per 1K completion tokens"],
    ]), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 14. API QUICK REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
def sec_api_ref():
    s = [sec_hdr("14.  API Quick Reference", INDIGO), sp(0.2)]
    s += [p("All endpoints require <tt>Authorization: Bearer {token}</tt> unless marked public. "
            "Base URL:  <tt>http://localhost:9380</tt>")]
    s += [sp(0.15)]

    def api_tbl(rows):
        t = Table(rows, colWidths=[5.5*cm, 10*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  DARK),
            ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,0),  8),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LIGHT_BG]),
            ("FONTNAME",      (0,1),(-1,-1), "Courier"),
            ("FONTSIZE",      (0,1),(-1,-1), 7.5),
            ("TEXTCOLOR",     (0,1),(-1,-1), SLATE),
            ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor("#CBD5E1")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ]))
        return t

    s += [h2("Auth & Users")]
    s += [api_tbl([
        ["Endpoint",                                  "Description"],
        ["POST /v1/auth/register",                    "Register new user"],
        ["POST /v1/auth/login",                       "Login (returns token)"],
        ["POST /v1/auth/logout",                      "Revoke session"],
        ["GET  /v1/auth/me",                          "Get current user profile"],
        ["POST /v1/auth/request-password-reset",      "Start password reset"],
        ["POST /v1/auth/reset-password",              "Complete password reset"],
        ["POST /v1/auth/mfa/setup",                   "Generate TOTP QR code"],
        ["POST /v1/auth/mfa/confirm",                 "Enable MFA"],
        ["POST /v1/auth/mfa/verify",                  "Verify TOTP on login"],
        ["POST /v1/auth/mfa/disable",                 "Disable MFA"],
        ["GET  /v1/auth/oidc/{provider}/login",       "Start OIDC login"],
        ["GET  /v1/auth/oidc/{provider}/callback",    "OIDC callback"],
        ["POST /v1/api-keys",                         "Create API key"],
        ["GET  /v1/api-keys",                         "List API keys"],
        ["POST /v1/api-keys/{id}/revoke",             "Revoke API key"],
    ]), sp(0.2)]

    s += [h2("Collections & Documents")]
    s += [api_tbl([
        ["Endpoint",                                       "Description"],
        ["GET    /v1/collections",                         "List collections"],
        ["POST   /v1/collections",                         "Create collection"],
        ["GET    /v1/collections/{id}",                    "Get collection"],
        ["PATCH  /v1/collections/{id}",                    "Update collection"],
        ["DELETE /v1/collections/{id}",                    "Delete collection"],
        ["GET    /v1/collections/{id}/graph",              "Knowledge graph triples"],
        ["GET    /v1/collections/{id}/members",            "List access members"],
        ["POST   /v1/collections/{id}/members",            "Add member (RBAC)"],
        ["GET    /v1/collections/{id}/documents",          "List documents"],
        ["POST   /v1/collections/{id}/documents/upload",   "Upload single file"],
        ["POST   /v1/collections/{id}/documents/bulk-upload","Batch upload (max 20)"],
        ["POST   /v1/documents/bulk",                      "Bulk delete / reindex / tag"],
        ["GET    /v1/documents/{id}",                      "Get document"],
        ["DELETE /v1/documents/{id}",                      "Delete document"],
        ["GET    /v1/documents/{id}/status",               "Indexing progress"],
        ["GET    /v1/documents/{id}/text",                 "Extracted text"],
        ["GET    /v1/documents/{id}/download-url",         "Pre-signed download URL"],
        ["GET    /v1/documents/{id}/graph",                "Document knowledge graph"],
        ["PUT    /v1/documents/{id}/tags",                 "Set document tags"],
        ["POST   /v1/documents/{id}/reindex",              "Re-index document"],
    ]), sp(0.2)]

    s += [h2("Retrieval & Chat")]
    s += [api_tbl([
        ["Endpoint",                                       "Description"],
        ["POST /v1/retrieve",                              "Hybrid search (vector + BM25 + HyDE)"],
        ["POST /v1/retrieve/stream",                       "Streaming search (SSE)"],
        ["POST /v1/retrieve/tool",                         "AI-driven tool-call retrieval"],
        ["GET  /v1/chunks/{id}",                           "Get single chunk"],
        ["GET  /v1/documents/{id}/chunks",                 "List document chunks"],
        ["GET  /v1/conversations",                         "List conversations"],
        ["POST /v1/conversations",                         "Create conversation"],
        ["GET  /v1/conversations/{id}",                    "Get conversation"],
        ["PATCH /v1/conversations/{id}",                   "Update conversation"],
        ["DELETE /v1/conversations/{id}",                  "Delete conversation"],
        ["GET  /v1/conversations/{id}/messages",           "List messages"],
        ["POST /v1/chat",                                  "Send message (streaming)"],
        ["POST /v1/chat/regenerate",                       "Regenerate last response"],
        ["GET  /v1/conversations/{id}/export",             "Export as JSON or Markdown"],
        ["POST /v1/conversations/{id}/fork",               "Fork conversation"],
    ]), sp(0.2)]

    s += [h2("Agents & Marketplace")]
    s += [api_tbl([
        ["Endpoint",                                           "Description"],
        ["GET    /v1/agents",                                  "List agents"],
        ["POST   /v1/agents",                                  "Create agent"],
        ["GET    /v1/agents/{id}",                             "Get agent"],
        ["PATCH  /v1/agents/{id}",                             "Update agent"],
        ["DELETE /v1/agents/{id}",                             "Delete agent"],
        ["POST   /v1/agents/{id}/runs",                        "Start run"],
        ["GET    /v1/agents/{id}/runs",                        "List runs"],
        ["GET    /v1/agents/{id}/runs/{rid}",                  "Get run status / output"],
        ["POST   /v1/agents/{id}/runs/{rid}/resume",           "Resume PAUSED run (HITL)"],
        ["POST   /v1/agents/{id}/runs/{rid}/replay",           "Time-travel replay"],
        ["DELETE /v1/agents/{id}/runs/{rid}",                  "Cancel run"],
        ["GET    /v1/agents/{id}/runs/{rid}/export",           "Export run log"],
        ["GET    /v1/marketplace/templates",                   "Browse templates"],
        ["GET    /v1/marketplace/templates/{id}",              "Get template definition"],
        ["POST   /v1/agents/import-template",                  "Import from marketplace or URL"],
    ]), sp(0.2)]

    s += [h2("Providers, Connectors, Deployments")]
    s += [api_tbl([
        ["Endpoint",                              "Description"],
        ["GET    /v1/providers",                  "List providers"],
        ["POST   /v1/providers",                  "Add provider (Anthropic/OpenAI/etc.)"],
        ["PATCH  /v1/providers/{id}",             "Update credentials or model"],
        ["DELETE /v1/providers/{id}",             "Remove provider"],
        ["GET    /v1/providers/{id}/models",      "List available models"],
        ["GET    /v1/connectors",                 "List connectors"],
        ["POST   /v1/connectors",                 "Create connector"],
        ["PATCH  /v1/connectors/{id}",            "Update connector"],
        ["DELETE /v1/connectors/{id}",            "Delete connector"],
        ["POST   /v1/connectors/{id}/sync",       "Trigger immediate sync"],
        ["GET    /v1/connectors/preview",         "Preview sync (dry run)"],
        ["GET    /v1/deployments",                "List deployments"],
        ["POST   /v1/deployments",                "Create public chat / webhook"],
        ["PATCH  /v1/deployments/{id}",           "Update deployment"],
        ["DELETE /v1/deployments/{id}",           "Delete deployment"],
        ["GET    /c/{slug}",                      "Public chat page (no auth)"],
        ["POST   /c/{slug}/chat",                 "Send message to public deployment"],
    ]), sp(0.2)]

    s += [h2("Teams, Admin & Observability")]
    s += [api_tbl([
        ["Endpoint",                              "Description"],
        ["GET  /v1/teams",                        "List teams"],
        ["POST /v1/teams",                        "Create team"],
        ["GET  /v1/tenants/current",              "Current tenant info"],
        ["GET  /v1/admin/users",                  "List all users (admin only)"],
        ["GET  /v1/admin/audit-events",           "Audit log (admin only)"],
        ["GET  /v1/observability/cost",           "LLM cost dashboard"],
        ["GET  /v1/observability/quality",        "Retrieval quality (NDCG, hit-rate)"],
        ["POST /v1/observability/retrieval-feedback","Submit search relevance feedback"],
        ["POST /v1/sandbox/run",                  "Run code directly (dev/testing)"],
        ["GET  /v1/health",                       "Health check (no auth needed)"],
        ["GET  /v1/metrics",                      "Prometheus metrics (no auth needed)"],
    ]), sp(0.3)]
    return s


# ══════════════════════════════════════════════════════════════════════════════
# BUILD
# ══════════════════════════════════════════════════════════════════════════════
def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2.2*cm,
        rightMargin=2.2*cm,
        topMargin=2.0*cm,
        bottomMargin=2.0*cm,
        title="OmniAI Complete Guide",
        author="OmniAI",
        subject="Full platform reference -- all milestones",
    )

    story = []
    story += cover()
    story += toc()
    story += sec_getting_started()
    story += sec_concepts()
    story += sec_documents()
    story += sec_retrieval()
    story += sec_chat()
    story += sec_providers()
    story += sec_agents()
    story += sec_deployments()
    story += sec_connectors()
    story += sec_identity()
    story += sec_observability()
    story += sec_security()
    story += sec_config()
    story += sec_api_ref()

    doc.build(story)
    sys.stdout.write(f"PDF written to: {OUTPUT}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    build()
