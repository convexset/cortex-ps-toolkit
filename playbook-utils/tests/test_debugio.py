"""Tests for DebugSink logging hooks."""

from __future__ import annotations

from playbook_utils.debugio import DebugSink, log_handler_context


def test_log_handler_routes_without_print(capsys) -> None:
    lines: list[str] = []

    with log_handler_context(lines.append):
        sink = DebugSink(None, verbose=True)
        sink.log("hello from refactor")

    assert lines == ["hello from refactor"]
    captured = capsys.readouterr()
    assert captured.out == ""


def test_verbose_print_when_no_handler(capsys) -> None:
    sink = DebugSink(None, verbose=True)
    sink.log("cli line")
    assert "cli line" in capsys.readouterr().out
