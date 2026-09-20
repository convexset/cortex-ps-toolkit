"""Pure-Python mirrors of small playbooks-analysis UI helper rules."""

from __future__ import annotations

import re


def structure_tree_playbook_name(line: str, line_index: int) -> str | None:
    trimmed = line.strip()
    if line_index == 0:
        return trimmed or None
    if "circular reference skipped" in trimmed:
        return None
    match = re.match(r"^\+-\s*(.+?)(\s+\(\d+x\))?(\s+\[MISSING\])?$", trimmed)
    return match.group(1).strip() if match else None


def test_structure_tree_playbook_name_root() -> None:
    assert structure_tree_playbook_name("Main PB", 0) == "Main PB"


def test_structure_tree_playbook_name_sub_with_count() -> None:
    assert structure_tree_playbook_name("    +- Sub PB (2x)", 1) == "Sub PB"


def test_structure_tree_playbook_name_circular() -> None:
    assert structure_tree_playbook_name("    +- (circular reference skipped)", 2) is None
