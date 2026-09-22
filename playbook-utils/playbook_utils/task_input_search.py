"""Search task inputs across a playbook tree (main playbook + sub-playbooks)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Set

from .cache import PlaybookCache
from .inspect import task_sort_key
from .keys import JsonDict, get_field, inner_task, task_name, task_type
from .playbook_tree import format_nesting_path, walk_playbook_tree

# Task-node fields that carry configuration / argument values.
_TASK_INPUT_FIELDS: tuple[str, ...] = (
    "scriptArguments",
    "arguments",
    "conditions",
    "message",
    "form",
    "loop",
    "timerTriggers",
    "fieldMapping",
)


def collect_task_inputs(node: Mapping[str, object]) -> JsonDict:
    """Return input-bearing fields from a task node (camelCase or lowercase)."""
    collected: JsonDict = {}
    for field_name in _TASK_INPUT_FIELDS:
        value = get_field(node, field_name)
        if value is not None:
            collected[field_name] = value
    inner = inner_task(node)
    if inner:
        inner_mapping = get_field(inner, "fieldMapping")
        if inner_mapping is not None:
            collected.setdefault("fieldMapping", inner_mapping)
    return collected


def serialize_task_inputs(node: Mapping[str, object]) -> str:
    """JSON-serialize task input fields for substring search."""
    payload = collect_task_inputs(node)
    if not payload:
        return ""
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def inputs_contain(node: Mapping[str, object], needle: str) -> bool:
    """Case-insensitive substring search over serialized task inputs."""
    if not needle:
        return False
    haystack = serialize_task_inputs(node)
    if not haystack:
        return False
    return needle.casefold() in haystack.casefold()


@dataclass
class TaskInputMatch:
    task_id: str
    task_name: str
    task_type: str
    containing_playbook_id: str
    containing_playbook_name: str
    nesting_path: List[str]
    unresolved_sub_playbook: Optional[str] = None

    @property
    def nesting_path_text(self) -> str:
        return format_nesting_path(self.nesting_path)

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "containing_playbook_id": self.containing_playbook_id,
            "containing_playbook_name": self.containing_playbook_name,
            "nesting_path": list(self.nesting_path),
            "nesting_path_text": self.nesting_path_text,
            "unresolved_sub_playbook": self.unresolved_sub_playbook,
        }


@dataclass
class TaskInputSearchResult:
    root_playbook_id: str
    root_playbook_name: str
    needle: str
    matches: List[TaskInputMatch] = field(default_factory=list)
    unresolved_sub_playbooks: List[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "root_playbook_id": self.root_playbook_id,
            "root_playbook_name": self.root_playbook_name,
            "needle": self.needle,
            "match_count": len(self.matches),
            "matches": [match.to_dict() for match in self.matches],
            "unresolved_sub_playbooks": list(self.unresolved_sub_playbooks),
        }


def search_task_inputs(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    needle: str,
) -> TaskInputSearchResult:
    """Find tasks whose serialized inputs contain ``needle`` (case-insensitive)."""
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    result = TaskInputSearchResult(
        root_playbook_id=root_id,
        root_playbook_name=root_name,
        needle=needle,
    )

    def visit_task(
        playbook: Mapping[str, object],
        path: List[str],
        task_id: str,
        node: Mapping[str, object],
    ) -> None:
        if not inputs_contain(node, needle):
            return
        playbook_id = str(playbook.get("id") or "")
        playbook_name = str(playbook.get("name") or playbook_id)
        result.matches.append(
            TaskInputMatch(
                task_id=task_id,
                task_name=task_name(node),
                task_type=task_type(node),
                containing_playbook_id=playbook_id,
                containing_playbook_name=playbook_name,
                nesting_path=list(path),
            )
        )

    result.unresolved_sub_playbooks = walk_playbook_tree(root_playbook, cache, visit_task)

    deduped: List[TaskInputMatch] = []
    seen_match_keys: Set[tuple[str, str, str]] = set()
    for match in result.matches:
        key = (match.containing_playbook_id, match.task_id, match.nesting_path_text)
        if key in seen_match_keys:
            continue
        seen_match_keys.add(key)
        deduped.append(match)
    result.matches = deduped
    result.matches.sort(
        key=lambda match: (
            match.nesting_path_text.lower(),
            task_sort_key(match.task_id),
            match.task_name.lower(),
        )
    )
    return result


def format_task_input_search_text(result: TaskInputSearchResult) -> str:
    lines = [
        f"Playbook: {result.root_playbook_name} ({result.root_playbook_id})",
        f"Needle: {result.needle!r}",
        f"Matches: {len(result.matches)}",
        "",
    ]
    if result.matches:
        lines.extend(
            [
                f"{'TASK':<8} {'TYPE':<12}  NAME",
                f"{'PATH'}",
                f"{'-'*8} {'-'*12}  {'-'*40}",
            ]
        )
        for match in result.matches:
            lines.append(
                f"{match.task_id:<8} {match.task_type:<12}  {match.task_name}"
            )
            lines.append(f"         {match.nesting_path_text}")
    else:
        lines.append("No matching tasks found.")

    if result.unresolved_sub_playbooks:
        lines.append("")
        lines.append(f"Unresolved sub-playbooks: {len(result.unresolved_sub_playbooks)}")
        for item in result.unresolved_sub_playbooks:
            lines.append(
                "  "
                f"{item['from_playbook']} task {item['from_task_id']} "
                f"({item['from_task_name']!r}) -> {item['sub_playbook_ref']!r}"
            )
    return "\n".join(lines)
