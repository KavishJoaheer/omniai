"""Generate the OmniAI Feature Guide PDF -- written simply for anyone to understand."""

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

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OmniAI_Feature_Guide.pdf")

# -- Colour palette ------------------------------------------------------------
INDIGO   = colors.HexColor("#4F46E5")
VIOLET   = colors.HexColor("#7C3AED")
TEAL     = colors.HexColor("#0D9488")
AMBER    = colors.HexColor("#D97706")
ROSE     = colors.HexColor("#E11D48")
SLATE    = colors.HexColor("#334155")
LIGHT_BG = colors.HexColor("#F8FAFC")
CARD_BG  = colors.HexColor("#EFF6FF")
CODE_BG  = colors.HexColor("#1E293B")
CODE_FG  = colors.HexColor("#E2E8F0")
MINT_BG  = colors.HexColor("#F0FDF4")
AMBER_BG = colors.HexColor("#FFFBEB")
ROSE_BG  = colors.HexColor("#FFF1F2")
WHITE    = colors.white
GREY     = colors.HexColor("#64748B")
DARK     = colors.HexColor("#0F172A")

# -- Styles --------------------------------------------------------------------
def S(name, **kw):
    return ParagraphStyle(name, **kw)

H1 = S("H1", fontName="Helvetica-Bold", fontSize=21, textColor=INDIGO,
       leading=28, spaceBefore=18, spaceAfter=8)
H2 = S("H2", fontName="Helvetica-Bold", fontSize=15, textColor=VIOLET,
       leading=21, spaceBefore=14, spaceAfter=6)
H3 = S("H3", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL,
       leading=17, spaceBefore=10, spaceAfter=4)
BODY = S("Body", fontName="Helvetica", fontSize=10.5, textColor=SLATE,
         leading=16, spaceAfter=5, alignment=TA_JUSTIFY)
BODY_BOLD = S("BodyBold", fontName="Helvetica-Bold", fontSize=10.5, textColor=DARK,
              leading=16, spaceAfter=4)
BULLET = S("Bullet", fontName="Helvetica", fontSize=10.5, textColor=SLATE,
           leading=16, leftIndent=16, firstLineIndent=-10, spaceAfter=2)
CODE = S("Code", fontName="Courier", fontSize=8.5, textColor=CODE_FG,
         leading=13, backColor=CODE_BG, leftIndent=8, rightIndent=8,
         spaceBefore=3, spaceAfter=3, borderPad=5)
NOTE = S("Note", fontName="Helvetica-Oblique", fontSize=10, textColor=AMBER,
         leading=15, spaceAfter=4)

# -- Helpers -------------------------------------------------------------------

def spacer(h=0.3):
    return Spacer(1, h * cm)

def hr(color=INDIGO, thickness=1.2):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=5)

def p(text, style=BODY):
    return Paragraph(text, style)

def h1(text): return Paragraph(text, H1)
def h2(text): return Paragraph(text, H2)
def h3(text): return Paragraph(text, H3)
def bold(text): return Paragraph(text, BODY_BOLD)

def bullets(items):
    return [Paragraph(f"&bull;  {item}", BULLET) for item in items]

def code_block(*lines):
    joined = "<br/>".join(
        line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace(" ", "&nbsp;")
        for line in lines
    )
    return Paragraph(joined, CODE)

def info_box(text, bg=CARD_BG, border=INDIGO, label=""):
    inner_style = S(f"IB_{id(text)}", fontName="Helvetica", fontSize=10,
                    textColor=DARK, leading=15)
    if label:
        text = f"<b>{label}</b>  {text}"
    row = [[Paragraph(text, inner_style)]]
    tbl = Table(row, colWidths=[15.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), bg),
        ("BOX",           (0,0),(-1,-1), 1.5, border),
        ("LEFTPADDING",   (0,0),(-1,-1), 11),
        ("RIGHTPADDING",  (0,0),(-1,-1), 11),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    return tbl

def data_table(rows, col_widths=None):
    col_widths = col_widths or [5*cm, 10.5*cm]
    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  INDIGO),
        ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
        ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,0),  9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LIGHT_BG]),
        ("FONTNAME",      (0,1),(-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1),(-1,-1), 8.5),
        ("TEXTCOLOR",     (0,1),(-1,-1), SLATE),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 7),
        ("RIGHTPADDING",  (0,0),(-1,-1), 7),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
    ]))
    return tbl

def section_header(title, color):
    style = S(f"SHdr_{id(title)}", fontName="Helvetica-Bold", fontSize=19,
               textColor=WHITE, leading=25)
    tbl = Table([[Paragraph(title, style)]], colWidths=[15.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 13),
        ("BOTTOMPADDING", (0,0),(-1,-1), 13),
        ("LEFTPADDING",   (0,0),(-1,-1), 14),
    ]))
    return tbl

# ==============================================================================
# COVER PAGE
# ==============================================================================

def cover_page():
    title_style = S("CoverTitle", fontName="Helvetica-Bold", fontSize=38,
                    textColor=WHITE, leading=46, alignment=TA_CENTER)
    sub_style   = S("CoverSub",   fontName="Helvetica-Bold", fontSize=20,
                    textColor=colors.HexColor("#A5B4FC"), leading=26, alignment=TA_CENTER)
    desc_style  = S("CoverDesc",  fontName="Helvetica-Oblique", fontSize=13,
                    textColor=colors.HexColor("#CBD5E1"), leading=19, alignment=TA_CENTER)
    ms_style    = S("CoverMS",    fontName="Helvetica", fontSize=11,
                    textColor=colors.HexColor("#818CF8"), leading=16, alignment=TA_CENTER)

    banner_rows = [
        [Paragraph("OmniAI", title_style)],
        [Paragraph("Feature Guide", sub_style)],
        [Spacer(1, 0.4*cm)],
        [Paragraph("Everything you need to know -- explained simply.", desc_style)],
        [Spacer(1, 0.4*cm)],
        [Paragraph("Milestones 18  *  19  *  20", ms_style)],
        [Spacer(1, 0.6*cm)],
    ]
    banner = Table(banner_rows, colWidths=[15.5*cm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), INDIGO),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))

    ms_label = S("MSL", fontName="Helvetica-Bold", fontSize=15, textColor=WHITE,
                  alignment=TA_CENTER)
    ms_title = S("MST", fontName="Helvetica-Bold", fontSize=11, textColor=DARK)
    ms_desc  = S("MSD", fontName="Helvetica",      fontSize=9.5, textColor=GREY)

    ms_rows = [
        [Paragraph("M18", ms_label),
         Paragraph("UX &amp; Accessibility", ms_title),
         Paragraph("Bulk actions, exports, dark mode, keyboard shortcuts", ms_desc)],
        [Paragraph("M19", ms_label),
         Paragraph("Advanced Retrieval", ms_title),
         Paragraph("HyDE search, multiple vector databases, streaming, tool calling", ms_desc)],
        [Paragraph("M20", ms_label),
         Paragraph("Agent Platform", ms_title),
         Paragraph("Parallel AI, pause &amp; approve, time-travel, marketplace, sandboxed code", ms_desc)],
    ]
    ms_tbl = Table(ms_rows, colWidths=[2.2*cm, 5*cm, 8.3*cm])
    ms_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS",  (0,0),(-1,-1), [MINT_BG, CARD_BG, ROSE_BG]),
        ("GRID",            (0,0),(-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",      (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",   (0,0),(-1,-1), 10),
        ("LEFTPADDING",     (0,0),(-1,-1), 9),
        ("RIGHTPADDING",    (0,0),(-1,-1), 9),
        ("VALIGN",          (0,0),(-1,-1), "MIDDLE"),
    ]))

    return [banner, spacer(0.7), ms_tbl, PageBreak()]


# ==============================================================================
# TABLE OF CONTENTS
# ==============================================================================

def toc():
    toc_head = S("TOCHead", fontName="Helvetica-Bold", fontSize=12,
                  textColor=INDIGO, leading=18, spaceBefore=10)
    toc_item = S("TOCItem", fontName="Helvetica", fontSize=10, textColor=SLATE, leading=16)

    sections = [
        ("M18 -- UX & Accessibility", [
            "1.  Bulk Document Operations",
            "2.  Conversation Export",
            "3.  Agent Run Export",
        ]),
        ("M19 -- Advanced Retrieval", [
            "4.  HyDE Query Expansion",
            "5.  pgvector / Pinecone / Weaviate Adapters",
            "6.  Streaming Search (Real-time Results)",
            "7.  Tool / Function Calling Retrieve",
            "8.  Multi-Modal Embeddings (Text + Images)",
            "9.  Conversation Forking",
        ]),
        ("M20 -- Agent Platform", [
            "10. Parallel Fan-Out / Join",
            "11. Human-in-the-Loop (Pause & Approve)",
            "12. Time-Travel Replay",
            "13. Agent Template Marketplace",
            "14. Multi-Language Code Nodes",
            "15. gVisor Sandbox (Extra-Safe Code Execution)",
            "16. Run Cost Tracking & Alerting",
        ]),
        ("Quick Reference", [
            "All API Endpoints",
            "Environment Variables",
            "Built-in Templates",
        ]),
    ]

    story = [h1("What's In This Guide"), hr(), spacer(0.1)]
    for sec_title, items in sections:
        story.append(Paragraph(sec_title, toc_head))
        for item in items:
            story.append(Paragraph(f"     {item}", toc_item))
        story.append(spacer(0.15))
    story.append(PageBreak())
    return story


# ==============================================================================
# M18
# ==============================================================================

def section_m18():
    story = [section_header("M18  --  UX & Accessibility", TEAL), spacer(0.3)]

    # 1. Bulk Documents
    story += [h2("1.  Bulk Document Operations"), hr(TEAL, 1)]
    story += [p(
        "<b>What is it?</b>  Instead of deleting or updating one document at a time, "
        "you can do it to <i>many</i> documents all at once -- like selecting lots of files "
        "on your desktop and pressing Delete."
    )]
    story += [p("<b>How to use it in the app:</b>")]
    story += bullets([
        "Open the <b>Knowledge</b> page.",
        "Tick the checkboxes next to the documents you want to change.",
        "A blue bar appears at the top -- choose <b>Delete</b>, <b>Re-index</b>, or <b>Set Tags</b>.",
    ])
    story += [spacer(0.15), p("<b>API (for developers):</b>")]
    story += [code_block(
        "POST /v1/documents/bulk",
        "{",
        '  "document_ids": ["doc_abc", "doc_def"],',
        '  "action": "delete"   // or: reindex | set_tags',
        "}",
    )]
    story += [spacer(0.1), info_box(
        "<b>The three actions:</b><br/>"
        "<b>delete</b> -- permanently removes the documents<br/>"
        "<b>reindex</b> -- re-reads the file and updates the search index<br/>"
        "<b>set_tags</b> -- attaches labels (like 'finance', '2025') to help you find them later",
        bg=MINT_BG, border=TEAL
    ), spacer(0.25)]

    # 2. Conversation Export
    story += [h2("2.  Conversation Export"), hr(TEAL, 1)]
    story += [p(
        "<b>What is it?</b>  Save any chat conversation to your computer as a neat document -- "
        "like taking a screenshot of a chat but as a real file you can open in Word or Notion."
    )]
    story += bullets([
        "Open the <b>Chat</b> page and select a conversation.",
        "Click <b>Download MD</b> (Markdown -- great for notes) or <b>Download JSON</b> (for developers).",
        "The file downloads automatically.",
    ])
    story += [spacer(0.1), code_block("GET /v1/conversations/{id}/export?format=markdown")]
    story += [spacer(0.1), info_box(
        "<b>Two formats:</b><br/>"
        "<b>Markdown (.md)</b> -- Looks like a nicely formatted document. Open in Notion, VSCode, or any text editor.<br/>"
        "<b>JSON (.json)</b> -- Raw data, useful if you want to process it with code.",
        bg=CARD_BG, border=INDIGO
    ), spacer(0.25)]

    # 3. Agent Run Export
    story += [h2("3.  Agent Run Export"), hr(TEAL, 1)]
    story += [p(
        "<b>What is it?</b>  An Agent is like an AI robot that does a job (searches your documents, "
        "runs calculations, writes answers). You can export a record of exactly what the robot did -- "
        "step by step -- so you can review, share, or archive it."
    )]
    story += bullets([
        "Go to the <b>Agents</b> page and open an agent.",
        "Find a run in the 'Latest output' panel.",
        "Click <b>Download MD</b> or <b>Download JSON</b>.",
    ])
    story += [spacer(0.1), code_block("GET /v1/agents/{id}/runs/{run_id}/export?format=json")]
    story += [spacer(0.4)]

    return story


# ==============================================================================
# M19
# ==============================================================================

def section_m19():
    story = [section_header("M19  --  Advanced Retrieval", VIOLET), spacer(0.3)]

    # 4. HyDE
    story += [h2("4.  HyDE Query Expansion"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  Normally when you search, the app looks for documents that match "
        "your words. HyDE is smarter -- before searching, it asks the AI to <i>imagine</i> "
        "what a perfect answer looks like, then searches for documents that match <i>that answer</i>. "
        "It's like asking a librarian to describe the ideal book, then finding it."
    )]
    story += [spacer(0.1), info_box(
        "<b>Example:</b>  You type 'What causes inflation?'  Without HyDE the app searches "
        "for those exact words.  With HyDE the AI first writes a short answer like "
        "'Inflation is caused by too much money chasing too few goods, supply shocks and central "
        "bank policy...'  then searches for documents about those ideas.  Much better results!",
        bg=AMBER_BG, border=AMBER
    ), spacer(0.15)]
    story += [p("<b>How to turn it on (API):</b>")]
    story += [code_block(
        "POST /v1/retrieve",
        "{",
        '  "query": "What causes inflation?",',
        '  "hyde": true,',
        '  "hyde_model": "gpt-4o"',
        "}",
    )]
    story += [p("If you don't have an AI model set up, it quietly falls back to normal search -- no errors.")]
    story += [spacer(0.25)]

    # 5. Vector DB Adapters
    story += [h2("5.  pgvector / Pinecone / Weaviate Adapters"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  OmniAI stores your documents as 'vectors' (numbers that describe "
        "the meaning of text). You can choose <i>where</i> these vectors are kept. "
        "Think of it as choosing which filing cabinet to use."
    )]
    story += [data_table(
        [
            ["SEARCH_KIND",  "What it is",                              "Best for"],
            ["memory",       "Stored in RAM (lost on restart)",          "Testing only"],
            ["pgvector",     "PostgreSQL with the pgvector extension",   "Self-hosted servers"],
            ["pinecone",     "Pinecone cloud service",                   "Easy cloud setup"],
            ["weaviate",     "Weaviate vector database",                 "Advanced search"],
        ],
        col_widths=[3*cm, 6.5*cm, 5*cm]
    ), spacer(0.15)]
    story += [p("<b>How to switch -- add one line to your .env file:</b>")]
    story += [code_block(
        "SEARCH_KIND=pgvector",
        "DATABASE_URL=postgresql://user:pass@localhost/omniai",
    )]
    story += [spacer(0.25)]

    # 6. Streaming SSE
    story += [h2("6.  Streaming Search (Real-time Results)"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  Normally the app waits until ALL results are found before "
        "showing them. Streaming shows results <i>as they arrive</i> -- one by one instantly. "
        "Think of it like watching a video load progressively vs waiting for the whole file."
    )]
    story += [code_block(
        "POST /v1/retrieve/stream",
        '{ "query": "What is quantum computing?", "top_k": 10 }',
        "",
        "// Each result arrives as a Server-Sent Event:",
        'data: { "text": "Quantum computers use qubits...", "score": 0.94 }',
        'data: { "text": "Unlike classical bits...", "score": 0.91 }',
        "data: [DONE]",
    )]
    story += [spacer(0.25)]

    # 7. Tool calling
    story += [h2("7.  Tool / Function Calling Retrieve"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  You can give AI models (like GPT-4) a special ability to search "
        "your documents <i>automatically</i> while answering a question. The AI decides when "
        "to search and what to search for -- you just ask a question and it does the rest."
    )]
    story += [code_block(
        "POST /v1/retrieve/tool",
        '{ "question": "Summarise our Q4 2025 financials", "top_k": 8 }',
        "",
        "// Response:",
        '{ "answer": "Q4 2025 revenue was...", "hits": [...], "tool_calls_made": 1 }',
    )]
    story += [spacer(0.25)]

    # 8. Multi-Modal
    story += [h2("8.  Multi-Modal Embeddings (Text + Images)"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  Normally you can only search text. With multi-modal embeddings "
        "you can also search using <b>images</b>. Send a photo and find documents that are "
        "visually or conceptually similar. Powered by the CLIP AI model."
    )]
    story += [info_box(
        "<b>How it works automatically:</b>  Any input starting with 'data:image/' is "
        "automatically routed to the CLIP image model.  Everything else goes to your normal "
        "text model.  No configuration needed!<br/><br/>"
        "<b>Install:</b>  pip install open-clip-torch torch Pillow",
        bg=MINT_BG, border=TEAL
    )]
    story += [spacer(0.25)]

    # 9. Conversation Fork
    story += [h2("9.  Conversation Forking"), hr(VIOLET, 1)]
    story += [p(
        "<b>What is it?</b>  Like saving a game checkpoint. You can 'fork' (branch off) a chat "
        "conversation at any point and try a different direction without losing the original. "
        "Perfect for exploring 'what if I had asked this differently?'"
    )]
    story += [code_block(
        "POST /v1/conversations/{id}/fork",
        "{",
        '  "title": "Alternative approach",',
        '  "fork_at_message_id": "msg_abc123"  // optional: fork from a specific message',
        "}",
    )]
    story += [spacer(0.4)]

    return story


# ==============================================================================
# M20
# ==============================================================================

def section_m20():
    story = [section_header("M20  --  Agent Platform", ROSE), spacer(0.3)]

    story += [info_box(
        "<b>What is an Agent?</b>  An Agent is like a little AI robot with a workflow. "
        "You draw a diagram (called a 'graph') that tells it what steps to follow -- "
        "search documents, run code, ask a human for approval, then write an answer. "
        "M20 makes agents much more powerful with new capabilities.",
        bg=ROSE_BG, border=ROSE
    ), spacer(0.3)]

    # 10. Fan-Out
    story += [h2("10.  Parallel Fan-Out / Join (Do Multiple Things at Once)"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Normally an agent does one thing at a time. With fan-out it can "
        "do <b>multiple searches simultaneously</b> -- like having several assistants look up "
        "different things at the same time, then combining all their findings."
    )]
    story += [data_table(
        [
            ["Node type", "What it does"],
            ["fan_out",   "Splits the workflow into multiple parallel paths"],
            ["retrieval", "(one per branch -- each can search a different document collection)"],
            ["join",      "Waits for ALL branches to finish, then combines all results"],
        ],
        col_widths=[3.5*cm, 12*cm]
    ), spacer(0.15)]
    story += [info_box(
        "<b>Real world example:</b>  You ask 'What are the legal and financial risks of this contract?' "
        "Fan-out searches <i>legal documents</i> AND <i>financial reports</i> at the same time. "
        "Join merges both sets of results. Your answer covers both topics -- twice as fast!",
        bg=AMBER_BG, border=AMBER
    ), spacer(0.25)]

    # 11. HITL
    story += [h2("11.  Human-in-the-Loop (Pause & Approve)"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Sometimes you want a <b>human to check the AI's work</b> before it "
        "proceeds -- like a teacher reviewing a student's answer before it gets sent out. "
        "The agent pauses, waits for your approval, then continues."
    )]
    story += [p("<b>How it works -- step by step:</b>")]
    story += bullets([
        "Add a <b>human_input</b> node anywhere in your agent's workflow.",
        "When the agent reaches that node, its status changes to <b>PAUSED</b>.",
        "Your app polls the run status and shows the context to a human reviewer.",
        "The human approves (or provides corrected text) via the resume endpoint.",
        "The agent continues from the next node automatically.",
    ])
    story += [spacer(0.15), p("<b>Resume a paused run:</b>")]
    story += [code_block(
        "POST /v1/agents/{agent_id}/runs/{run_id}/resume",
        "{",
        '  "human_input": "Looks correct, please proceed.",',
        '  "approved": true',
        "}",
    )]
    story += [spacer(0.1), info_box(
        "<b>Perfect for:</b>  Compliance workflows where a manager must approve before an "
        "AI-generated email or report is sent.  Medical or legal contexts where accuracy is critical.",
        bg=MINT_BG, border=TEAL
    ), spacer(0.25)]

    # 12. Time-travel
    story += [h2("12.  Time-Travel Replay (Debug from Any Point)"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Every agent run is recorded like a video -- every step is logged. "
        "You can 'rewind' to any moment and <b>replay the run from that point</b> with different "
        "inputs. Like using Ctrl+Z -- but for AI workflows."
    )]
    story += [p("<b>When is this useful?</b>")]
    story += bullets([
        "An agent gave a wrong answer -- rewind to just before 'Generate' and try different context.",
        "You want to test 'what if' scenarios without re-running the full expensive pipeline.",
        "Debugging a step that failed -- skip directly to that step and re-run it.",
    ])
    story += [spacer(0.1), p("<b>How to use it:</b>")]
    story += [code_block(
        "POST /v1/agents/{agent_id}/runs/{run_id}/replay",
        "{",
        '  "from_event": 3,',
        '  "input_override": "Try this different question instead"',
        "}",
        "",
        "// Returns a brand-new run that:",
        "// - fast-forwards through events 0-2 (from the stored recording)",
        "// - then continues LIVE from event 3 with your new input",
    )]
    story += [spacer(0.25)]

    # 13. Marketplace
    story += [h2("13.  Agent Template Marketplace"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Ready-made agent blueprints you can use instantly -- "
        "like downloading a free template from the internet and editing it to fit your needs. "
        "No need to build from scratch."
    )]
    story += [data_table(
        [
            ["Template ID",       "Name",                  "What it does"],
            ["basic-rag",         "Basic RAG",              "Search then answer. The simplest setup."],
            ["parallel-research", "Parallel Research",      "Search two knowledge bases at the same time."],
            ["human-review",      "Human-in-the-Loop",      "Pause for a human to approve before answering."],
            ["code-executor",     "Code Executor",          "Search context then run a Python script."],
            ["summarisation",     "Document Summarisation", "Find 10 passages and write a summary."],
        ],
        col_widths=[4.2*cm, 4.3*cm, 7*cm]
    ), spacer(0.15)]
    story += [p("<b>Import a template in one API call:</b>")]
    story += [code_block(
        "POST /v1/agents/import-template",
        "{",
        '  "template_id": "parallel-research",',
        '  "name": "My Research Agent"',
        "}",
    )]
    story += [spacer(0.1), p("<b>Or import from your own URL</b> (share templates with your team):")]
    story += [code_block(
        "POST /v1/agents/import-template",
        '{ "url": "https://your-server.com/my-template.json" }',
    )]
    story += [spacer(0.25)]

    # 14. Multi-language code
    story += [h2("14.  Multi-Language Code Nodes"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Agent 'code nodes' can now run <b>Python, JavaScript, or Bash</b> "
        "-- not just Python. Each language automatically gets the user's question and retrieved "
        "context as variables."
    )]
    story += [data_table(
        [
            ["Language",   "Variables available",         "Example use"],
            ["Python",     "user_input, context_text",    "Data analysis, maths, file processing"],
            ["JavaScript", "user_input, context_text",    "Web logic, JSON manipulation"],
            ["Bash",       "$USER_INPUT, $CONTEXT_TEXT",  "Shell commands, file operations"],
        ],
        col_widths=[3*cm, 5.5*cm, 7*cm]
    ), spacer(0.15)]
    story += [code_block(
        "// JavaScript code node example:",
        "const wordCount = context_text.split(' ').length;",
        "console.log(`Found ${wordCount} words in the retrieved context.`);",
    )]
    story += [spacer(0.25)]

    # 15. gVisor
    story += [h2("15.  gVisor Sandbox (Extra-Safe Code Execution)"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  When agents run code, there's a risk it could do something "
        "dangerous (like read secret files). A sandbox is like a 'glass box' -- the code "
        "runs inside it but cannot touch anything outside. gVisor is the strongest option."
    )]
    story += [data_table(
        [
            ["SANDBOX_KIND", "Safety level",                       "Requirements"],
            ["none",         "No sandbox -- code nodes disabled",  "Nothing"],
            ["subprocess",   "Basic -- runs in a separate process", "Nothing extra"],
            ["docker",       "Good -- Docker container isolation",  "Docker installed"],
            ["gvisor",       "Best -- intercepts all system calls", "gVisor (runsc) installed"],
        ],
        col_widths=[3.2*cm, 6.3*cm, 6*cm]
    ), spacer(0.15)]
    story += [p("<b>Set it in your .env file:</b>")]
    story += [code_block(
        "SANDBOX_KIND=gvisor",
        "GVISOR_RUNSC_BIN=/usr/local/bin/runsc",
    )]
    story += [spacer(0.1), info_box(
        "<b>No gVisor? No problem.</b>  If the runsc binary isn't found, OmniAI automatically "
        "falls back to 'subprocess' mode and logs a warning.  You won't get an error -- it "
        "just uses the next-best option silently.",
        bg=MINT_BG, border=TEAL
    ), spacer(0.25)]

    # 16. Cost tracking
    story += [h2("16.  Run Cost Tracking & Alerting"), hr(ROSE, 1)]
    story += [p(
        "<b>What is it?</b>  Every agent run now shows you how much it cost (estimated in USD, "
        "based on how many AI tokens were used). You can also set a budget limit -- if any "
        "single run costs more than that, you get a warning in the logs."
    )]
    story += [p("<b>Set a cost alert in your .env:</b>")]
    story += [code_block(
        "AGENT_RUN_COST_ALERT_USD=0.10   # warn if a run costs more than $0.10",
    )]
    story += [p("<b>See the cost when checking a run:</b>")]
    story += [code_block(
        "GET /v1/agents/{id}/runs/{run_id}",
        "",
        '{ "cost_usd": 0.0042, "status": "COMPLETED", ... }',
    )]
    story += [spacer(0.4)]

    return story


# ==============================================================================
# QUICK REFERENCE
# ==============================================================================

def quick_reference():
    story = [h1("Quick Reference"), hr(), spacer(0.1)]

    story += [h2("All New API Endpoints")]
    story += [data_table(
        [
            ["Method + Path",                                      "What it does"],
            ["POST /v1/documents/bulk",                            "Delete / re-index / tag many documents at once"],
            ["GET  /v1/conversations/{id}/export",                 "Download a chat as JSON or Markdown"],
            ["POST /v1/conversations/{id}/fork",                   "Branch a conversation from a checkpoint"],
            ["GET  /v1/agents/{id}/runs/{run_id}/export",          "Download an agent run as JSON or Markdown"],
            ["POST /v1/retrieve",                                  "Search documents (add hyde:true for HyDE)"],
            ["POST /v1/retrieve/stream",                           "Streaming search -- results appear one by one"],
            ["POST /v1/retrieve/tool",                             "AI searches your docs automatically while answering"],
            ["GET  /v1/marketplace/templates",                     "Browse ready-made agent blueprints"],
            ["GET  /v1/marketplace/templates/{id}",                "See the full blueprint for one template"],
            ["POST /v1/agents/import-template",                    "Create an agent from a blueprint or URL"],
            ["POST /v1/agents/{id}/runs/{run_id}/resume",          "Approve and continue a paused (HITL) run"],
            ["POST /v1/agents/{id}/runs/{run_id}/replay",          "Time-travel: re-run from any event in history"],
        ],
        col_widths=[7.8*cm, 7.7*cm]
    ), spacer(0.35)]

    story += [h2("Key Environment Variables")]
    story += [data_table(
        [
            ["Variable",                    "What it does",                           "Default"],
            ["SEARCH_KIND",                 "Which vector database to use",           "memory"],
            ["SANDBOX_KIND",                "How to run agent code safely",           "none"],
            ["AGENT_RUN_COST_ALERT_USD",    "Alert when a run exceeds this cost ($)", "0 (off)"],
            ["AGENT_MARKETPLACE_URL",       "Custom template registry URL",           "(built-in)"],
            ["GVISOR_RUNSC_BIN",            "Path to gVisor runsc binary",            "runsc"],
            ["PINECONE_API_KEY",            "Your Pinecone API key",                  "--"],
            ["WEAVIATE_URL",                "URL of your Weaviate server",            "localhost:8080"],
        ],
        col_widths=[5.5*cm, 6.5*cm, 3.5*cm]
    ), spacer(0.35)]

    story += [h2("Getting Started in 3 Steps")]
    story += [info_box(
        "<b>Step 1:</b>  Log in with your admin account (default: admin@omniai.local)<br/><br/>"
        "<b>Step 2:</b>  Upload documents to a Collection in the Knowledge page<br/><br/>"
        "<b>Step 3:</b>  Go to Agents, click 'Import Template', choose 'basic-rag', "
        "give it a name, and run it!  Ask it a question about your uploaded documents.",
        bg=CARD_BG, border=INDIGO
    ), spacer(0.3)]

    story += [h2("Test Coverage")]
    story += [info_box(
        "<b>339 automated tests</b> cover all features described in this guide -- "
        "all green.  To run them:<br/><br/>"
        "cd backend<br/>"
        "python -m pytest --tb=short -q",
        bg=MINT_BG, border=TEAL
    )]

    return story


# ==============================================================================
# BUILD
# ==============================================================================

def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2.5*cm,
        rightMargin=2.5*cm,
        topMargin=2.2*cm,
        bottomMargin=2.2*cm,
        title="OmniAI Feature Guide",
        author="OmniAI",
        subject="Feature guide for milestones M18, M19, M20",
    )

    story = []
    story += cover_page()
    story += toc()
    story += section_m18()
    story += section_m19()
    story += section_m20()
    story += quick_reference()

    doc.build(story)
    sys.stdout.write(f"PDF written to: {OUTPUT}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    build()
