"""Search task outputs across a playbook tree (main playbook + sub-playbooks)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Set

from .cache import PlaybookCache
from .inspect import task_sort_key
from .keys import JsonDict, get_field, inner_task, task_name, task_type
from .playbook_tree import format_nesting_path, walk_playbook_tree

# Task-node fields that describe values written to context / issue / sub-playbooks.
_TASK_OUTPUT_FIELDS: tuple[str, ...] = (
    "scriptArguments",
    "arguments",
    "fieldMapping",
)


def script_binding_candidates(inner: Mapping[str, object]) -> List[str]:
    """Return script/command identifiers from an inner task."""
    candidates: List[str] = []
    for field_name in ("script", "scriptId", "scriptName"):
        value = get_field(inner, field_name)
        if value:
            candidates.append(str(value))
    return candidates


def script_command_name(binding: str) -> str:
    """Normalize ``Builtin|||setIssue`` to ``setIssue``."""
    text = binding.strip()
    if "|||" in text:
        return text.rsplit("|||", 1)[-1]
    return text


def script_filter_matches(inner: Mapping[str, object], script_filter: str) -> bool:
    """Match a task binding to a script/command filter (exact command name)."""
    wanted = script_filter.strip().casefold()
    if not wanted:
        return True
    for candidate in script_binding_candidates(inner):
        command = script_command_name(candidate).casefold()
        if command == wanted:
            return True
        if candidate.casefold() == wanted:
            return True
    return False


def collect_task_outputs(node: Mapping[str, object]) -> JsonDict:
    """Return output-bearing fields from a task node."""
    collected: JsonDict = {}
    for field_name in _TASK_OUTPUT_FIELDS:
        value = get_field(node, field_name)
        if value is not None:
            collected[field_name] = value

    inner = inner_task(node)
    if inner:
        inner_mapping = get_field(inner, "fieldMapping")
        if inner_mapping is not None:
            collected.setdefault("fieldMapping", inner_mapping)
    return collected


def serialize_task_outputs(node: Mapping[str, object]) -> str:
    payload = collect_task_outputs(node)
    if not payload:
        return ""
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def _field_matches_needle(field_name: str, value: object, needle_fold: str) -> bool:
    if needle_fold in str(field_name).casefold():
        return True
    blob = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return needle_fold in blob.casefold()


def matched_output_fields(node: Mapping[str, object], needle: str) -> List[str]:
    """Return output field names whose key or value contains ``needle``."""
    if not needle:
        return []
    needle_fold = needle.casefold()
    matched: List[str] = []
    script_args = get_field(node, "scriptArguments")
    if isinstance(script_args, dict):
        for key, value in script_args.items():
            if _field_matches_needle(str(key), value, needle_fold):
                matched.append(str(key))
    arguments = get_field(node, "arguments")
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            key_str = str(key)
            if key_str in matched:
                continue
            if _field_matches_needle(key_str, value, needle_fold):
                matched.append(key_str)
    return matched


def outputs_contain(node: Mapping[str, object], needle: str) -> bool:
    if not needle:
        return False
    haystack = serialize_task_outputs(node)
    if not haystack:
        return False
    return needle.casefold() in haystack.casefold()


@dataclass
class TaskOutputMatch:
    task_id: str
    task_name: str
    task_type: str
    script_binding: str
    containing_playbook_id: str
    containing_playbook_name: str
    nesting_path: List[str]
    matched_fields: List[str] = field(default_factory=list)

    @property
    def nesting_path_text(self) -> str:
        return format_nesting_path(self.nesting_path)

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "script_binding": self.script_binding,
            "containing_playbook_id": self.containing_playbook_id,
            "containing_playbook_name": self.containing_playbook_name,
            "nesting_path": list(self.nesting_path),
            "nesting_path_text": self.nesting_path_text,
            "matched_fields": list(self.matched_fields),
        }


@dataclass
class TaskOutputSearchResult:
    root_playbook_id: str
    root_playbook_name: str
    needle: str
    script_filter: Optional[str]
    matches: List[TaskOutputMatch] = field(default_factory=list)
    unresolved_sub_playbooks: List[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "root_playbook_id": self.root_playbook_id,
            "root_playbook_name": self.root_playbook_name,
            "needle": self.needle,
            "script_filter": self.script_filter,
            "match_count": len(self.matches),
            "matches": [match.to_dict() for match in self.matches],
            "unresolved_sub_playbooks": list(self.unresolved_sub_playbooks),
        }


def _primary_script_binding(inner: Mapping[str, object]) -> str:
    candidates = script_binding_candidates(inner)
    return candidates[0] if candidates else ""


def search_task_outputs(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    needle: str,
    *,
    script_filter: Optional[str] = None,
) -> TaskOutputSearchResult:
    """Find tasks whose serialized outputs contain ``needle`` (case-insensitive)."""
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    result = TaskOutputSearchResult(
        root_playbook_id=root_id,
        root_playbook_name=root_name,
        needle=needle,
        script_filter=script_filter,
    )

    def visit_task(
        playbook: Mapping[str, object],
        path: List[str],
        task_id: str,
        node: Mapping[str, object],
    ) -> None:
        inner = inner_task(node)
        if script_filter and (not inner or not script_filter_matches(inner, script_filter)):
            return
        if not outputs_contain(node, needle):
            return
        playbook_id = str(playbook.get("id") or "")
        playbook_name = str(playbook.get("name") or playbook_id)
        result.matches.append(
            TaskOutputMatch(
                task_id=task_id,
                task_name=task_name(node),
                task_type=task_type(node),
                script_binding=_primary_script_binding(inner) if inner else "",
                containing_playbook_id=playbook_id,
                containing_playbook_name=playbook_name,
                nesting_path=list(path),
                matched_fields=matched_output_fields(node, needle),
            )
        )

    result.unresolved_sub_playbooks = walk_playbook_tree(root_playbook, cache, visit_task)

    deduped: List[TaskOutputMatch] = []
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


def format_task_output_search_text(result: TaskOutputSearchResult) -> str:
    lines = [
        f"Playbook: {result.root_playbook_name} ({result.root_playbook_id})",
        f"Needle: {result.needle!r}",
    ]
    if result.script_filter:
        lines.append(f"Script filter: {result.script_filter!r}")
    lines.extend([f"Matches: {len(result.matches)}", ""])
    if result.matches:
        lines.extend(
            [
                f"{'TASK':<8} {'TYPE':<12} {'SCRIPT':<22}  NAME",
                f"{'OUTPUTS'} / PATH",
                f"{'-'*8} {'-'*12} {'-'*22}  {'-'*40}",
            ]
        )
        for match in result.matches:
            outputs = ", ".join(match.matched_fields) if match.matched_fields else "—"
            lines.append(
                f"{match.task_id:<8} {match.task_type:<12} {match.script_binding:<22}  {match.task_name}"
            )
            lines.append(f"         {outputs}")
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
