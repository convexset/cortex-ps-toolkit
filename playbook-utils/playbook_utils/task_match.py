"""Match playbook tasks by title using contains or equals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Mapping, Sequence

from .keys import playbook_tasks, task_name
from .task_checks import check_regular_script_task

MatchMode = Literal["contains", "equals"]


@dataclass(frozen=True)
class TaskNameMatch:
    mode: MatchMode
    pattern: str
    case_sensitive: bool = True

    def matches(self, title: str) -> bool:
        hay = title if self.case_sensitive else title.lower()
        needle = self.pattern if self.case_sensitive else self.pattern.lower()
        if self.mode == "contains":
            return needle in hay
        return hay == needle


def parse_task_name_match(spec: str) -> TaskNameMatch:
    """Parse ``contains:pattern``, ``equals:pattern``, optional trailing ``:i`` for case-insensitive."""
    text = spec.strip()
    if not text:
        raise ValueError("task name match spec is empty")

    case_sensitive = True
    if text.endswith(":i"):
        case_sensitive = False
        text = text[:-2]

    if text.startswith("contains:"):
        pattern = text[len("contains:") :]
        if not pattern:
            raise ValueError(f"contains match missing pattern: {spec!r}")
        return TaskNameMatch("contains", pattern, case_sensitive)

    if text.startswith("equals:"):
        pattern = text[len("equals:") :]
        if not pattern:
            raise ValueError(f"equals match missing pattern: {spec!r}")
        return TaskNameMatch("equals", pattern, case_sensitive)

    return TaskNameMatch("contains", text, case_sensitive)


def parse_post_task_update_spec(spec: str) -> tuple[TaskNameMatch, str]:
    """Parse ``MATCH|actions`` for post-refactor in-place updates."""
    if "|" not in spec:
        raise ValueError(
            f"post-task-update must look like MATCH|actions (got {spec!r}); "
            "example: contains:HttpV2:i|retry=20x30,stop-on-error"
        )
    match_part, actions_part = spec.split("|", 1)
    match_part = match_part.strip()
    actions_part = actions_part.strip()
    if not match_part or not actions_part:
        raise ValueError(f"post-task-update missing match or actions: {spec!r}")
    return parse_task_name_match(match_part), actions_part


def find_matching_regular_script_task_ids(
    playbook: Mapping[str, object],
    matches: Sequence[TaskNameMatch],
) -> List[str]:
    """Return sorted task ids whose titles match any rule and are regular script tasks."""
    if not matches:
        return []
    found: List[str] = []
    for tid, node in playbook_tasks(playbook).items():
        title = task_name(node)
        if not any(matcher.matches(title) for matcher in matches):
            continue
        try:
            check_regular_script_task(node, str(tid))
        except ValueError:
            continue
        found.append(str(tid))
    return sorted(set(found))
