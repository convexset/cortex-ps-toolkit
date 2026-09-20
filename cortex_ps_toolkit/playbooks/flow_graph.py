"""Per-playbook task flow graphs for analysis UI (nodes, edges, reachability)."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from ..content.yaml_codec import dumps_yaml
from .entity_resolution import integration_command_from_task, resolve_automation_script
from .graph import _reachable_nodes, build_expanded_graph
from .resolver import CachePlaybookResolver
from .yaml_export import rename_playbook_keys_for_yaml
from .yaml_helpers import (
    playbook_identity,
    playbook_key,
    resolve_start_task_id,
    script_label,
    sub_playbook_reference,
    task_field,
)


def _format_edge_condition(condition: str) -> str:
    text = str(condition or "").strip()
    if text == "#default#":
        return "ELSE"
    if text in ("#none#", ""):
        return ""
    if text.startswith("#") and text.endswith("#"):
        return text[1:-1]
    return text


def _task_detail(
    node: dict[str, Any],
    task_type: str,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
) -> Optional[str]:
    inner = node.get("task") or {}
    if task_type == "playbook":
        _pid, pname = sub_playbook_reference(inner)
        return pname or None
    if task_type == "regular":
        label = script_label(node, script_by_id=script_by_id, script_by_name=script_by_name)
        return label if label and label != str(inner.get("name") or "") else None
    return None


def _task_metadata(
    node: dict[str, Any],
    task_type: str,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    inner = node.get("task") or {}
    meta: dict[str, Any] = {}
    description = inner.get("description")
    if description:
        meta["description"] = str(description)

    if task_type == "playbook":
        pid, pname = sub_playbook_reference(inner)
        if pid:
            meta["playbook_id"] = pid
        if pname:
            meta["playbook_name"] = pname
        return meta

    if task_type != "regular":
        return meta

    integration = integration_command_from_task(node, script_by_id=script_by_id)
    if integration:
        meta["is_command"] = True
        meta["command"] = integration.get("command")
        if integration.get("raw"):
            meta["command_raw"] = integration.get("raw")
        return meta

    automation = resolve_automation_script(
        node,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )
    if automation:
        meta["is_command"] = False
        meta["script_name"] = automation.canonical_name
        if automation.script_id:
            meta["script_id"] = automation.script_id
        if automation.command_raw:
            meta["script_binding"] = automation.command_raw
        return meta

    script_name = task_field(inner, "scriptName")
    if script_name:
        meta["script_name"] = str(script_name)
    script_id = task_field(inner, "scriptId")
    if script_id:
        meta["script_id"] = str(script_id)
    return meta


def _reachable_task_ids_in_playbook(tasks: Mapping[str, Any], start_id: str) -> set[str]:
    if not start_id or start_id not in tasks:
        return set()
    seen: set[str] = set()
    queue = [start_id]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        node = tasks.get(current) or {}
        next_tasks = node.get("nextTasks") or node.get("nexttasks") or {}
        for targets in next_tasks.values():
            if not isinstance(targets, list):
                continue
            for target_id in targets:
                target = str(target_id)
                if target in tasks:
                    queue.append(target)
    return seen


def build_playbook_flow_graph(
    playbook: dict[str, Any],
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
    reachable_task_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Build task nodes and labeled edges from ``nextTasks`` for one playbook file."""
    tasks = playbook.get("tasks") or {}
    start_id = resolve_start_task_id(playbook)
    local_reachable = _reachable_task_ids_in_playbook(tasks, start_id)
    if reachable_task_ids is None:
        reachable_task_ids = local_reachable

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for task_id, node in tasks.items():
        task_type = str(node.get("type") or "unknown")
        inner = node.get("task") or {}
        label = str(inner.get("name") or task_id)
        detail = _task_detail(
            node,
            task_type,
            script_by_id=script_by_id,
            script_by_name=script_by_name,
        )
        task_copy = copy.deepcopy(node)
        nodes.append({
            "id": str(task_id),
            "task_type": task_type,
            "label": label,
            "detail": detail,
            "reachable": str(task_id) in reachable_task_ids,
            "is_start": str(task_id) == start_id or task_type == "start",
            "raw_task": task_copy,
            "raw_task_yaml": dumps_yaml(rename_playbook_keys_for_yaml(task_copy)),
            **_task_metadata(
                node,
                task_type,
                script_by_id=script_by_id,
                script_by_name=script_by_name,
            ),
        })

        next_tasks = node.get("nextTasks") or node.get("nexttasks") or {}
        for condition, targets in next_tasks.items():
            if not isinstance(targets, list):
                continue
            cond_label = _format_edge_condition(str(condition))
            for target_id in targets:
                target = str(target_id)
                edge_key = (str(task_id), target, cond_label)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append({
                    "from": str(task_id),
                    "to": target,
                    "condition": cond_label,
                })

    nodes.sort(key=lambda row: (int(row["id"]) if str(row["id"]).isdigit() else row["id"]))
    return {
        "start_task_id": start_id,
        "nodes": nodes,
        "edges": edges,
    }


def build_flow_graphs_for_tree(
    playbooks_in_tree: list[dict[str, Any]],
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
    *,
    script_by_id: Mapping[str, Mapping[str, Any]],
    script_by_name: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Flow graphs for root + sub-playbooks; reachability from expanded execution graph."""
    start, adjacency, _nodes, _keys = build_expanded_graph(root_playbook, resolver)
    expanded_reachable = {
        (node.playbook_key, node.task_id)
        for node in _reachable_nodes(start, adjacency)
    }

    graphs: list[dict[str, Any]] = []
    for entry in sorted(
        playbooks_in_tree,
        key=lambda row: (row.get("role") != "root", row.get("name") or ""),
    ):
        pb_id = str(entry.get("id") or "")
        if not pb_id:
            continue
        playbook = resolver.load(pb_id)
        pb_key = playbook_key(playbook)
        _pb_id, pb_name = playbook_identity(playbook)
        reachable_ids = {
            task_id
            for key, task_id in expanded_reachable
            if key == pb_key
        }
        graph = build_playbook_flow_graph(
            playbook,
            script_by_id=script_by_id,
            script_by_name=script_by_name,
            reachable_task_ids=reachable_ids,
        )
        graphs.append({
            "playbook_id": pb_id,
            "playbook_name": pb_name,
            "role": entry.get("role"),
            "graph": graph,
        })
    return graphs
