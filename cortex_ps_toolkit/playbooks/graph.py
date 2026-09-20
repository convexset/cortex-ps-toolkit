"""Expanded playbook graph: reachability and path-to-completion metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from .entity_resolution import integration_command_from_task, resolve_automation_script
from .resolver import CachePlaybookResolver
from .yaml_helpers import (
    next_task_ids,
    playbook_identity,
    playbook_key,
    resolve_start_task_id,
    script_label,
    sub_playbook_reference,
)

ROOT_INSTANCE = "root"


@dataclass(frozen=True)
class TaskNode:
    instance: str
    playbook_key: str
    task_id: str


def _parent_call(instance: str) -> tuple[str, str] | None:
    if instance == ROOT_INSTANCE:
        return None
    parent_instance, call_task_id = instance.rsplit("/", 1)
    return parent_instance, call_task_id


def build_expanded_graph(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> tuple[TaskNode, dict[TaskNode, list[TaskNode]], dict[TaskNode, dict[str, Any]], dict[str, str]]:
    """Build expanded adjacency list inlining sub-playbook calls (returns to parent)."""
    start_id = resolve_start_task_id(root_playbook)
    root_key = playbook_key(root_playbook)
    start_node = TaskNode(ROOT_INSTANCE, root_key, start_id)

    adjacency: dict[TaskNode, list[TaskNode]] = {}
    nodes: dict[TaskNode, dict[str, Any]] = {}
    instance_playbook_keys: dict[str, str] = {ROOT_INSTANCE: root_key}

    def add_edge(source: TaskNode, target: TaskNode) -> None:
        adjacency.setdefault(source, [])
        if target not in adjacency[source]:
            adjacency[source].append(target)

    def expand(node: TaskNode, active_sub_playbooks: tuple[str, ...]) -> None:
        if node in nodes:
            return

        instance_playbook_keys.setdefault(node.instance, node.playbook_key)
        playbook = resolver.load_by_key(node.playbook_key)
        tasks = playbook.get("tasks") or {}
        task = tasks.get(node.task_id)
        if task is None:
            return

        nodes[node] = task
        task_type = str(task.get("type") or "unknown")

        if task_type == "playbook":
            inner = task.get("task") or {}
            pid, pname = sub_playbook_reference(inner)
            target_id = resolver.resolve(pid, pname)
            if target_id:
                sub_playbook = resolver.load(target_id)
                sub_key = playbook_key(sub_playbook)
                frame = f"{node.instance}/{node.task_id}:{sub_key}"
                if frame not in active_sub_playbooks:
                    sub_instance = f"{node.instance}/{node.task_id}"
                    instance_playbook_keys[sub_instance] = sub_key
                    sub_start = resolve_start_task_id(sub_playbook)
                    sub_node = TaskNode(sub_instance, sub_key, sub_start)
                    add_edge(node, sub_node)
                    expand(sub_node, active_sub_playbooks + (frame,))
            return

        for successor_id in next_task_ids(task):
            successor = TaskNode(node.instance, node.playbook_key, successor_id)
            add_edge(node, successor)
            expand(successor, active_sub_playbooks)

        if not next_task_ids(task):
            parent = _parent_call(node.instance)
            if parent is not None:
                parent_instance, call_task_id = parent
                parent_key = instance_playbook_keys.get(parent_instance, root_key)
                parent_tasks = resolver.load_by_key(parent_key).get("tasks") or {}
                call_task = parent_tasks.get(call_task_id) or {}
                for successor_id in next_task_ids(call_task):
                    successor = TaskNode(parent_instance, parent_key, successor_id)
                    add_edge(node, successor)
                    expand(successor, active_sub_playbooks)

    expand(start_node, ())
    return start_node, adjacency, nodes, instance_playbook_keys


def _reachable_nodes(start: TaskNode, adjacency: dict[TaskNode, list[TaskNode]]) -> set[TaskNode]:
    seen: set[TaskNode] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, ()))
    return seen


def _terminal_nodes(reachable: set[TaskNode], adjacency: dict[TaskNode, list[TaskNode]]) -> set[TaskNode]:
    return {node for node in reachable if not adjacency.get(node)}


def _topological_order(
    nodes: set[TaskNode],
    adjacency: dict[TaskNode, list[TaskNode]],
) -> list[TaskNode]:
    indegree: dict[TaskNode, int] = {node: 0 for node in nodes}
    for source in nodes:
        for target in adjacency.get(source, ()):
            if target in indegree:
                indegree[target] += 1

    queue = [node for node, degree in indegree.items() if degree == 0]
    order: list[TaskNode] = []
    while queue:
        current = queue.pop(0)
        order.append(current)
        for successor in adjacency.get(current, ()):
            if successor not in indegree:
                continue
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    return order


def _longest_path_in_dag(
    start: TaskNode,
    target: TaskNode,
    adjacency: dict[TaskNode, list[TaskNode]],
    nodes: set[TaskNode],
) -> tuple[int, list[TaskNode]]:
    order = _topological_order(nodes, adjacency)
    best_length: dict[TaskNode, int] = {}
    best_pred: dict[TaskNode, TaskNode | None] = {}

    for node in order:
        if node == start:
            best_length[node] = 1
        predecessors = [
            predecessor
            for predecessor in order
            if predecessor in best_length and node in adjacency.get(predecessor, ())
        ]
        if predecessors:
            predecessor = max(predecessors, key=lambda item: best_length[item])
            candidate = best_length[predecessor] + 1
            if node not in best_length or candidate > best_length[node]:
                best_length[node] = candidate
                best_pred[node] = predecessor

    if target not in best_length:
        return 0, []

    path: list[TaskNode] = []
    current: TaskNode | None = target
    while current is not None:
        path.append(current)
        if current == start:
            break
        current = best_pred.get(current)
    path.reverse()
    return best_length[target], path


def _min_path_to_target(
    start: TaskNode,
    adjacency: dict[TaskNode, list[TaskNode]],
    target: TaskNode,
) -> tuple[int | None, list[TaskNode]]:
    queue: list[tuple[TaskNode, int, list[TaskNode]]] = [(start, 1, [start])]
    visited: dict[TaskNode, int] = {}

    while queue:
        current, depth, path = queue.pop(0)
        if current == target:
            return depth, path
        if current in visited and visited[current] <= depth:
            continue
        visited[current] = depth
        for successor in adjacency.get(current, ()):
            queue.append((successor, depth + 1, path + [successor]))
    return None, []


def compute_completion_path_metrics(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> dict[str, Any]:
    """Shortest/longest sequential task count from start to any completion (recursive subs)."""
    start, adjacency, _nodes, _keys = build_expanded_graph(root_playbook, resolver)
    reachable = _reachable_nodes(start, adjacency)
    terminals = _terminal_nodes(reachable, adjacency)

    if not reachable:
        return {
            "min_tasks_to_completion": None,
            "max_tasks_to_completion": None,
            "terminal_count": 0,
            "reachable_task_steps": 0,
            "note": "No reachable tasks from start.",
        }

    if not terminals:
        return {
            "min_tasks_to_completion": None,
            "max_tasks_to_completion": None,
            "terminal_count": 0,
            "reachable_task_steps": len(reachable),
            "note": "No terminal completion nodes (possible cycle or open branch).",
        }

    min_len: int | None = None
    max_len = 0
    for terminal in terminals:
        shortest, _ = _min_path_to_target(start, adjacency, terminal)
        if shortest is not None:
            min_len = shortest if min_len is None else min(min_len, shortest)
        longest, _ = _longest_path_in_dag(start, terminal, adjacency, reachable)
        if longest > max_len:
            max_len = longest

    return {
        "min_tasks_to_completion": min_len,
        "max_tasks_to_completion": max_len if max_len > 0 else None,
        "terminal_count": len(terminals),
        "reachable_task_steps": len(reachable),
        "note": None,
    }


def _format_edge_condition(condition: str) -> str:
    text = str(condition or "").strip()
    if text == "#default#":
        return "ELSE"
    if text in ("#none#", ""):
        return ""
    if text.startswith("#") and text.endswith("#"):
        return text[1:-1]
    return text


@dataclass
class _TaskSummaryBucket:
    count: int = 0
    scripts: set[str] = field(default_factory=set)
    playbooks: set[str] = field(default_factory=set)
    commands: set[str] = field(default_factory=set)


def _playbook_task_sort_key(task_id: str) -> tuple[int, str]:
    text = str(task_id)
    return (0, f"{int(text):020d}") if text.isdigit() else (1, text)


def compute_conditional_branches_by_task(playbook: dict[str, Any]) -> dict[str, set[str]]:
    """Union of condition-branch names on any path from playbook start to each task."""
    tasks = playbook.get("tasks") or {}
    if not tasks:
        return {}

    reverse: dict[str, list[tuple[str, str]]] = defaultdict(list)
    task_types: dict[str, str] = {}
    for tid, node in tasks.items():
        task_id = str(tid)
        task_types[task_id] = str(node.get("type") or "unknown")
        next_tasks = node.get("nextTasks") or node.get("nexttasks") or {}
        for condition, targets in next_tasks.items():
            if not isinstance(targets, list):
                continue
            label = _format_edge_condition(str(condition))
            for target in targets:
                reverse[str(target)].append((task_id, label))

    memo: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def union_for(task_id: str) -> set[str]:
        if task_id in memo:
            return memo[task_id]
        if task_id in visiting:
            return set()
        visiting.add(task_id)
        acc: set[str] = set()
        for pred_id, edge_label in reverse.get(task_id, []):
            pred_branches = union_for(pred_id)
            path_branches = set(pred_branches)
            if task_types.get(pred_id) == "condition" and edge_label:
                path_branches.add(edge_label)
            acc |= path_branches
        visiting.remove(task_id)
        memo[task_id] = acc
        return acc

    return {str(tid): union_for(str(tid)) for tid in tasks}


def _task_binding_sets(
    node: dict[str, Any],
    task_type: str,
    *,
    script_by_id: dict[str, dict[str, Any]] | None,
    script_by_name: dict[str, dict[str, Any]] | None,
) -> tuple[set[str], set[str], set[str]]:
    script_by_id = script_by_id or {}
    script_by_name = script_by_name or {}
    scripts: set[str] = set()
    playbooks: set[str] = set()
    commands: set[str] = set()
    inner = node.get("task") or {}

    if task_type == "playbook":
        pid, pname = sub_playbook_reference(inner)
        if pname:
            playbooks.add(str(pname))
        elif pid:
            playbooks.add(str(pid))
        return scripts, playbooks, commands

    if task_type != "regular":
        return scripts, playbooks, commands

    integration = integration_command_from_task(node, script_by_id=script_by_id)
    if integration and integration.get("command"):
        commands.add(str(integration["command"]))
        return scripts, playbooks, commands

    automation = resolve_automation_script(
        node,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )
    if automation and automation.canonical_name:
        scripts.add(str(automation.canonical_name))
        return scripts, playbooks, commands

    label = script_label(node, script_by_id=script_by_id, script_by_name=script_by_name)
    if label:
        scripts.add(str(label))
    return scripts, playbooks, commands


def _summary_bucket_to_row(key: tuple[str, str], bucket: _TaskSummaryBucket) -> dict[str, Any]:
    return {
        "task_type": key[0],
        "label": key[1],
        "count": bucket.count,
        "scripts": sorted(bucket.scripts),
        "playbooks": sorted(bucket.playbooks),
        "commands": sorted(bucket.commands),
    }


def _sorted_summary_rows(buckets: dict[tuple[str, str], _TaskSummaryBucket]) -> list[dict[str, Any]]:
    return [
        _summary_bucket_to_row(key, bucket)
        for key, bucket in sorted(
            buckets.items(),
            key=lambda item: (-item[1].count, item[0][0], item[0][1]),
        )
    ]


def _add_task_to_bucket(
    bucket: _TaskSummaryBucket,
    *,
    scripts: set[str],
    playbooks: set[str],
    commands: set[str],
) -> None:
    bucket.count += 1
    bucket.scripts |= scripts
    bucket.playbooks |= playbooks
    bucket.commands |= commands


def _expanded_path_metrics_for_instances(
    start: TaskNode,
    instances: list[TaskNode],
    adjacency: dict[TaskNode, list[TaskNode]],
    reachable: set[TaskNode],
    terminals: set[TaskNode],
) -> dict[str, Any]:
    reachable_instances = [item for item in instances if item in reachable]
    if not reachable_instances:
        return {
            "expanded_reachable": False,
            "min_steps_from_start": None,
            "max_steps_from_start": None,
            "min_steps_to_terminal": None,
            "max_steps_to_terminal": None,
        }

    min_from_start: int | None = None
    max_from_start: int | None = None
    min_to_terminal: int | None = None
    max_to_terminal: int | None = None

    for inst in reachable_instances:
        shortest_from, _ = _min_path_to_target(start, adjacency, inst)
        if shortest_from is not None:
            min_from_start = shortest_from if min_from_start is None else min(min_from_start, shortest_from)
        longest_from, _ = _longest_path_in_dag(start, inst, adjacency, reachable)
        if longest_from > 0:
            max_from_start = longest_from if max_from_start is None else max(max_from_start, longest_from)

        for terminal in terminals:
            shortest_to, _ = _min_path_to_target(inst, adjacency, terminal)
            if shortest_to is not None:
                min_to_terminal = shortest_to if min_to_terminal is None else min(min_to_terminal, shortest_to)
            longest_to, _ = _longest_path_in_dag(inst, terminal, adjacency, reachable)
            if longest_to > 0:
                max_to_terminal = longest_to if max_to_terminal is None else max(max_to_terminal, longest_to)

    return {
        "expanded_reachable": True,
        "min_steps_from_start": min_from_start,
        "max_steps_from_start": max_from_start,
        "min_steps_to_terminal": min_to_terminal,
        "max_steps_to_terminal": max_to_terminal,
    }


def compute_playbook_task_listings(
    playbooks_in_tree: list[dict[str, Any]],
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
    *,
    script_by_id: dict[str, dict[str, Any]] | None = None,
    script_by_name: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One row per task in each playbook file, with expanded-graph path metrics."""
    start, adjacency, expanded_nodes, _keys = build_expanded_graph(root_playbook, resolver)
    reachable_nodes = _reachable_nodes(start, adjacency)
    reachable_task_keys = {(node.playbook_key, node.task_id) for node in reachable_nodes}
    terminals = _terminal_nodes(reachable_nodes, adjacency)

    instances_by_key: dict[tuple[str, str], list[TaskNode]] = defaultdict(list)
    for node in expanded_nodes:
        instances_by_key[(node.playbook_key, node.task_id)].append(node)

    listings: list[dict[str, Any]] = []
    branch_cache: dict[str, dict[str, set[str]]] = {}

    for entry in sorted(playbooks_in_tree, key=lambda row: (row.get("role") != "root", row.get("name") or "")):
        pb_id = str(entry.get("id") or "")
        if not pb_id:
            continue
        playbook = resolver.load(pb_id)
        _pb_id, pb_name = playbook_identity(playbook)
        pb_key = playbook_key(playbook)
        if pb_id not in branch_cache:
            branch_cache[pb_id] = compute_conditional_branches_by_task(playbook)
        branches_by_task = branch_cache[pb_id]

        task_rows: list[dict[str, Any]] = []
        tasks = playbook.get("tasks") or {}
        for task_id in sorted(tasks.keys(), key=_playbook_task_sort_key):
            node = tasks[task_id]
            tid = str(task_id)
            task_type = str(node.get("type") or "unknown")
            inner = node.get("task") or {}
            title = str(inner.get("name") or tid)
            label = script_label(node, script_by_id=script_by_id, script_by_name=script_by_name)
            scripts, playbooks, commands = _task_binding_sets(
                node,
                task_type,
                script_by_id=script_by_id,
                script_by_name=script_by_name,
            )
            path_metrics = _expanded_path_metrics_for_instances(
                start,
                instances_by_key.get((pb_key, tid), []),
                adjacency,
                reachable_nodes,
                terminals,
            )
            task_rows.append(
                {
                    "task_id": tid,
                    "title": title,
                    "task_type": task_type,
                    "label": label,
                    "scripts": sorted(scripts),
                    "playbooks": sorted(playbooks),
                    "commands": sorted(commands),
                    "conditional_branches": sorted(branches_by_task.get(tid, set())),
                    **path_metrics,
                    "expanded_reachable": (pb_key, tid) in reachable_task_keys,
                }
            )

        listings.append(
            {
                "playbook_id": pb_id,
                "playbook_name": pb_name,
                "role": entry.get("role"),
                "tasks": task_rows,
            }
        )

    return listings


def compute_task_summaries(
    playbooks_in_tree: list[dict[str, Any]],
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
    *,
    script_by_id: dict[str, dict[str, Any]] | None = None,
    script_by_name: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Reachable, unreachable, and all-task summaries with script/playbook/command bindings."""
    _start, adjacency, _nodes, _keys = build_expanded_graph(root_playbook, resolver)
    reachable_task_keys = {(node.playbook_key, node.task_id) for node in _reachable_nodes(_start, adjacency)}

    reachable_buckets: dict[tuple[str, str], _TaskSummaryBucket] = defaultdict(_TaskSummaryBucket)
    unreachable_buckets: dict[tuple[str, str], _TaskSummaryBucket] = defaultdict(_TaskSummaryBucket)
    all_buckets: dict[tuple[str, str], _TaskSummaryBucket] = defaultdict(_TaskSummaryBucket)
    totals = {"reachable": 0, "unreachable": 0, "total": 0}

    for entry in playbooks_in_tree:
        pb_id = str(entry.get("id") or "")
        if not pb_id:
            continue
        playbook = resolver.load(pb_id)
        pb_key = playbook_key(playbook)

        for task_id, node in (playbook.get("tasks") or {}).items():
            totals["total"] += 1
            tid = str(task_id)
            task_type = str(node.get("type") or "unknown")
            label = script_label(node, script_by_id=script_by_id, script_by_name=script_by_name)
            key = (task_type, label)
            scripts, playbooks, commands = _task_binding_sets(
                node,
                task_type,
                script_by_id=script_by_id,
                script_by_name=script_by_name,
            )

            _add_task_to_bucket(
                all_buckets[key],
                scripts=scripts,
                playbooks=playbooks,
                commands=commands,
            )

            if (pb_key, tid) in reachable_task_keys:
                _add_task_to_bucket(
                    reachable_buckets[key],
                    scripts=scripts,
                    playbooks=playbooks,
                    commands=commands,
                )
                totals["reachable"] += 1
            else:
                _add_task_to_bucket(
                    unreachable_buckets[key],
                    scripts=scripts,
                    playbooks=playbooks,
                    commands=commands,
                )
                totals["unreachable"] += 1

    return (
        _sorted_summary_rows(reachable_buckets),
        _sorted_summary_rows(unreachable_buckets),
        _sorted_summary_rows(all_buckets),
        totals,
    )


def compute_task_summaries_by_reachability(
    playbooks_in_tree: list[dict[str, Any]],
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
    *,
    script_by_id: dict[str, dict[str, Any]] | None = None,
    script_by_name: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Split task summary into reachable vs unreachable (expanded graph, recursive subs)."""
    reachable, unreachable, _all_rows, totals = compute_task_summaries(
        playbooks_in_tree,
        root_playbook,
        resolver,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )
    return reachable, unreachable, totals
