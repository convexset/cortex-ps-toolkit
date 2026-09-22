"""Shared playbook-tree traversal (root playbook + sub-playbooks)."""

from __future__ import annotations

from typing import Callable, List, Mapping, Optional, Sequence, Set

from .cache import PlaybookCache
from .inspect import task_sort_key
from .keys import JsonDict, get_field, inner_task, playbook_tasks, task_name, task_type

TaskVisitor = Callable[
    [Mapping[str, object], List[str], str, Mapping[str, object]],
    None,
]


def format_nesting_path(path: Sequence[str]) -> str:
    """Join playbook names from root to the containing playbook."""
    cleaned = [str(part) for part in path if str(part)]
    return " > ".join(cleaned)


def resolve_sub_playbook(
    cache: PlaybookCache,
    node: Mapping[str, object],
) -> Optional[JsonDict]:
    inner = inner_task(node)
    if not inner:
        return None
    playbook_id = get_field(inner, "playbookId")
    playbook_name = get_field(inner, "playbookName")
    if playbook_id:
        try:
            return cache.get(str(playbook_id))
        except KeyError:
            pass
    if playbook_name:
        try:
            return cache.resolve(str(playbook_name))
        except KeyError:
            pass
    return None


def sub_playbook_label(node: Mapping[str, object]) -> str:
    inner = inner_task(node)
    playbook_name = get_field(inner, "playbookName") if inner else None
    playbook_id = get_field(inner, "playbookId") if inner else None
    return str(playbook_name or playbook_id or task_name(node) or "?")


def walk_playbook_tree(
    root_playbook: Mapping[str, object],
    cache: PlaybookCache,
    visit_task: TaskVisitor,
) -> List[JsonDict]:
    """Walk tasks in ``root_playbook`` and reachable sub-playbooks."""
    unresolved: List[JsonDict] = []
    seen_unresolved: Set[str] = set()
    root_id = str(root_playbook.get("id") or "")
    root_name = str(root_playbook.get("name") or root_id)

    def visit(playbook: Mapping[str, object], path: List[str], chain: Set[str]) -> None:
        playbook_id = str(playbook.get("id") or "")
        playbook_name = str(playbook.get("name") or playbook_id)
        current_path = path if path else [playbook_name]

        for task_id, node in sorted(playbook_tasks(playbook).items(), key=lambda item: task_sort_key(item[0])):
            visit_task(playbook, current_path, task_id, node)

            if task_type(node) != "playbook":
                continue

            sub = resolve_sub_playbook(cache, node)
            if sub is None:
                label = sub_playbook_label(node)
                key = f"{playbook_id}:{task_id}:{label}"
                if key not in seen_unresolved:
                    seen_unresolved.add(key)
                    unresolved.append(
                        {
                            "from_playbook": playbook_name,
                            "from_task_id": task_id,
                            "from_task_name": task_name(node),
                            "sub_playbook_ref": label,
                        }
                    )
                continue

            sub_id = str(sub.get("id") or "")
            sub_name = str(sub.get("name") or sub_id)
            if sub_id and sub_id in chain:
                continue
            next_chain = set(chain)
            if sub_id:
                next_chain.add(sub_id)
            visit(sub, current_path + [sub_name], next_chain)

    visit(root_playbook, [root_name], {root_id} if root_id else set())
    return unresolved
