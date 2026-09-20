"""Mirrors for error-handling match preview helpers (see refactor-graph-validation.js)."""

from __future__ import annotations


def task_title_matches(
    *,
    match_mode: str,
    pattern: str,
    case_insensitive: bool,
    title: str,
) -> bool:
    needle = pattern if not case_insensitive else pattern.lower()
    hay = title if not case_insensitive else title.lower()
    if match_mode == "equals":
        return hay == needle
    return needle in hay


def test_task_title_matches_contains_case_insensitive() -> None:
    assert task_title_matches(
        match_mode="contains",
        pattern="httpv2",
        case_insensitive=True,
        title="Update Case | HttpV2",
    )


def test_task_title_matches_equals() -> None:
    assert task_title_matches(
        match_mode="equals",
        pattern="Step A",
        case_insensitive=False,
        title="Step A",
    )
