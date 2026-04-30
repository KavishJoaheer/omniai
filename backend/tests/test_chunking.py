from __future__ import annotations

from omniai.plugins.chunk_templates.general import GeneralChunkTemplate
from omniai.plugins.chunk_templates.qa import QaChunkTemplate
from omniai.plugins.chunk_templates.sentence_window import SentenceWindowChunkTemplate
from omniai.plugins.chunk_templates.small_to_big import SmallToBigChunkTemplate


def test_general_template_returns_chunks_for_long_text():
    template = GeneralChunkTemplate()
    text = "Paragraph one is here. " * 50
    specs = template.chunk(text=text, document_metadata={"filename": "x.txt"})
    assert specs, "general template should produce chunks for long text"
    assert all(spec.text for spec in specs)


def test_qa_template_chunks_on_headings():
    template = QaChunkTemplate()
    text = "# Question 1\nThe answer.\n\n# Question 2\nAnother answer."
    specs = template.chunk(text=text, document_metadata={"filename": "x.md"})
    assert len(specs) >= 2


def test_small_to_big_creates_parent_and_children():
    template = SmallToBigChunkTemplate(parent_size=50, child_size=15, child_overlap=3)
    text = " ".join([f"word{i}" for i in range(200)])
    specs = template.chunk(text=text, document_metadata={"filename": "x.txt"})
    parents = [s for s in specs if s.metadata.get("chunk_kind") == "parent"]
    children = [s for s in specs if s.metadata.get("chunk_kind") == "child"]
    assert len(parents) >= 2, "should have multiple parent windows"
    assert len(children) >= len(parents), "each parent should yield at least one child"
    assert all(s.metadata.get("is_indexable") is False for s in parents)
    assert all(s.metadata.get("is_indexable") is True for s in children)


def test_sentence_window_template_handles_simple_text():
    template = SentenceWindowChunkTemplate()
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    specs = template.chunk(text=text, document_metadata={"filename": "x.txt"})
    assert specs
