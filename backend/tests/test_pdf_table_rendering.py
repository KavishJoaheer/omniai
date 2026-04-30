from __future__ import annotations

from omniai.plugins.parsers.pdf import _render_table_as_markdown


def test_render_table_as_markdown_basic():
    table = [
        ["Country", "Capital"],
        ["France", "Paris"],
        ["Japan", "Tokyo"],
    ]
    rendered = _render_table_as_markdown(table)
    assert "| Country | Capital |" in rendered
    assert "| --- | --- |" in rendered
    assert "| France | Paris |" in rendered
    assert "| Japan | Tokyo |" in rendered


def test_render_table_handles_none_cells_and_pipe_chars():
    table = [
        ["a", "b|c"],
        [None, "d"],
    ]
    rendered = _render_table_as_markdown(table)
    assert "b\\|c" in rendered  # pipes escaped
    assert "|  | d |" in rendered  # None became empty


def test_render_table_returns_empty_for_empty_input():
    assert _render_table_as_markdown([]) == ""
    assert _render_table_as_markdown([[]]) == ""
