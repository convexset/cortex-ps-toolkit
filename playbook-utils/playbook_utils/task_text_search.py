"""Full-text search across tasks in a playbook tree."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Set

from .cache import PlaybookCache
from .inspect import task_sort_key
from .keys import JsonDict, inner_task, playbook_tasks, task_name, task_type
from .playbook_tree import format_nesting_path, walk_playbook_tree
from .task_summary import compact_task_summary, format_compact_task_summary

# Drop canvas / server metadata; keep task logic and bindings.
_TASK_TEXT_DROP_KEYS = frozenset(
    {
        "view",
        "taskId",
        "taskid",
        "version",
        "cacheVersn",
        "cacheversn",
        "modified",
        "created",
        "sizeInBytes",
        "sizeinbytes",
        "sequenceNumber",
        "sequencenumber",
        "primaryTerm",
        "primaryterm",
        "evidenceData",
        "evidencedata",
    }
)


def _strip_task_metadata(value: object) -> object:
    if isinstance(value, Mapping):
        cleaned: JsonDict = {}
        for key, item in value.items():
            if str(key) in _TASK_TEXT_DROP_KEYS:
                continue
            cleaned[str(key)] = _strip_task_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_task_metadata(item) for item in value]
    return value


def serialize_task_text(node: Mapping[str, object]) -> str:
    """JSON-serialize a task node (minus canvas metadata) for substring search."""
    payload = _strip_task_metadata(dict(node))
    inner = inner_task(node)
    if inner:
        payload["task"] = _strip_task_metadata(dict(inner))
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def task_text_contains(node: Mapping[str, object], needle: str) -> bool:
    if not needle:
        return False
    haystack = serialize_task_text(node)
    if not haystack:
        return False
    return needle.casefold() in haystack.casefold()


@dataclass
class TaskTextMatch:
    task_id: str
    task_name: str
    task_type: str
    containing_playbook_id: str
    containing_playbook_name: str
    nesting_path: List[str]
    task_summary: JsonDict

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
            "task_summary": dict(self.task_summary),
        }


@dataclass
class TaskTextSearchResult:
    root_playbook_id: str
    root_playbook_name: str
    needle: str
    matches: List[TaskTextMatch] = field(default_factory=list)
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


def search_task_text(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    needle: str,
    *,
    name_contains: Optional[str] = None,
) -> TaskTextSearchResult:
    """Find tasks whose serialized content contains ``needle`` (case-insensitive)."""
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    result = TaskTextSearchResult(
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
        if not task_text_contains(node, needle):
            return
        task_label = task_name(node)
        if name_contains and name_contains.casefold() not in task_label.casefold():
            return
        playbook_id = str(playbook.get("id") or "")
        playbook_name = str(playbook.get("name") or playbook_id)
        result.matches.append(
            TaskTextMatch(
                task_id=task_id,
                task_name=task_label,
                task_type=task_type(node),
                containing_playbook_id=playbook_id,
                containing_playbook_name=playbook_name,
                nesting_path=list(path),
                task_summary=compact_task_summary(node),
            )
        )

    result.unresolved_sub_playbooks = walk_playbook_tree(root_playbook, cache, visit_task)

    deduped: List[TaskTextMatch] = []
    seen: Set[tuple[str, str, str]] = set()
    for match in result.matches:
        key = (match.containing_playbook_id, match.task_id, match.nesting_path_text)
        if key in seen:
            continue
        seen.add(key)
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


def format_task_text_search_agent(result: TaskTextSearchResult) -> str:
    lines = [
        f"Playbook: {result.root_playbook_name} ({result.root_playbook_id})",
        f"Needle: {result.needle!r}",
        f"Matches: {len(result.matches)}",
        "",
    ]
    if not result.matches:
        lines.append("No matching tasks found.")
    else:
        for index, match in enumerate(result.matches, start=1):
            if index > 1:
                lines.append("")
            lines.append(
                format_compact_task_summary(
                    match.task_id,
                    match.task_summary,
                    playbook_name=match.containing_playbook_name,
                    nesting_path=match.nesting_path_text,
                )
            )
    if result.unresolved_sub_playbooks:
        lines.extend(["", f"Unresolved sub-playbooks: {len(result.unresolved_sub_playbooks)}"])
        for item in result.unresolved_sub_playbooks:
            lines.append(
                "  "
                f"{item['from_playbook']} task {item['from_task_id']} "
                f"({item['from_task_name']!r}) -> {item['sub_playbook_ref']!r}"
            )
    return "\n".join(lines)


def format_task_text_search_text(result: TaskTextSearchResult) -> str:
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
