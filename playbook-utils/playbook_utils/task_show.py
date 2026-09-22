"""Show compact task summaries for agent review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional

from .cache import PlaybookCache
from .condition_branches import locate_condition_task
from .inspect import task_sort_key
from .keys import JsonDict, playbook_tasks, task_name, task_type
from .playbook_tree import format_nesting_path, walk_playbook_tree
from .task_summary import compact_task_summary, format_compact_task_summary


@dataclass
class TaskShowEntry:
    task_id: str
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
            "containing_playbook_id": self.containing_playbook_id,
            "containing_playbook_name": self.containing_playbook_name,
            "nesting_path": list(self.nesting_path),
            "nesting_path_text": self.nesting_path_text,
            "task_summary": dict(self.task_summary),
        }


@dataclass
class TaskShowResult:
    root_playbook_id: str
    root_playbook_name: str
    query: JsonDict
    tasks: List[TaskShowEntry] = field(default_factory=list)
    unresolved_sub_playbooks: List[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "root_playbook_id": self.root_playbook_id,
            "root_playbook_name": self.root_playbook_name,
            "query": dict(self.query),
            "task_count": len(self.tasks),
            "tasks": [entry.to_dict() for entry in self.tasks],
            "unresolved_sub_playbooks": list(self.unresolved_sub_playbooks),
        }


def show_task_by_ref(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    task_ref: str,
) -> TaskShowResult:
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    playbook, task_id, path = locate_condition_task(root_playbook, cache, task_ref)
    node = playbook_tasks(playbook)[task_id]
    result = TaskShowResult(
        root_playbook_id=root_id,
        root_playbook_name=root_name,
        query={"task": task_ref},
    )
    result.tasks.append(
        TaskShowEntry(
            task_id=task_id,
            containing_playbook_id=str(playbook.get("id") or ""),
            containing_playbook_name=str(playbook.get("name") or ""),
            nesting_path=list(path),
            task_summary=compact_task_summary(node),
        )
    )
    return result


def show_tasks_by_name(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    name_contains: str,
) -> TaskShowResult:
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)
    result = TaskShowResult(
        root_playbook_id=root_id,
        root_playbook_name=root_name,
        query={"name_contains": name_contains},
    )
    needle = name_contains.casefold()

    def visit_task(
        playbook: Mapping[str, object],
        path: List[str],
        task_id: str,
        node: Mapping[str, object],
    ) -> None:
        if needle not in task_name(node).casefold():
            return
        result.tasks.append(
            TaskShowEntry(
                task_id=task_id,
                containing_playbook_id=str(playbook.get("id") or ""),
                containing_playbook_name=str(playbook.get("name") or ""),
                nesting_path=list(path),
                task_summary=compact_task_summary(node),
            )
        )

    result.unresolved_sub_playbooks = walk_playbook_tree(root_playbook, cache, visit_task)
    result.tasks.sort(
        key=lambda entry: (
            entry.nesting_path_text.lower(),
            task_sort_key(entry.task_id),
            str(entry.task_summary.get("name") or "").lower(),
        )
    )
    return result


def format_task_show_agent(result: TaskShowResult) -> str:
    lines = [
        f"Playbook: {result.root_playbook_name} ({result.root_playbook_id})",
        f"Query: {result.query}",
        f"Tasks: {len(result.tasks)}",
        "",
    ]
    if not result.tasks:
        lines.append("No tasks found.")
    else:
        for index, entry in enumerate(result.tasks, start=1):
            if index > 1:
                lines.append("")
            lines.append(
                format_compact_task_summary(
                    entry.task_id,
                    entry.task_summary,
                    playbook_name=entry.containing_playbook_name,
                    nesting_path=entry.nesting_path_text,
                )
            )
    if result.unresolved_sub_playbooks:
        lines.extend(["", f"Unresolved sub-playbooks: {len(result.unresolved_sub_playbooks)}"])
    return "\n".join(lines)
