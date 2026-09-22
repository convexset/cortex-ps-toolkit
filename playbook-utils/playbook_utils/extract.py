"""Build a sub-playbook from a potential root, and rewrite a parent copy."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .fields import FieldPolicy
from .graph import ClusterExtractCheckResult, PotentialRootResult, check_potential_root, descendant_ids
from .keys import (
    JsonDict,
    next_tasks_map,
    normalize_playbook,
    parse_view,
    playbook_tasks,
    pop_field,
    set_canonical,
    set_task_position,
    task_position,
    task_type,
)
from .yaml_codec import new_uuid


DEFAULT_VIEW_PADDING = 400.0
DEFAULT_START_POSITION = (50.0, 50.0)


def refactor_subplaybook_name(
    main_playbook_name: str,
    task_name: str,
    *,
    task_id: str,
) -> str:
    """Name for an extracted leaf sub-playbook (task id avoids title collisions)."""
    del task_name
    return f"[REFACTOR-S] {main_playbook_name} [LEAF from {task_id}]"


def refactor_cluster_subplaybook_name(
    main_playbook_name: str,
    start_name: str,
    end_name: str,
    *,
    start_task_id: str,
    end_task_id: str,
) -> str:
    """Name for an extracted intermediate cluster sub-playbook."""
    del start_name, end_name
    return f"[REFACTOR-S] {main_playbook_name} [INT from {start_task_id} to {end_task_id}]"


def refactor_parent_copy_name(
    main_playbook_name: str,
    at: Optional[datetime] = None,
) -> str:
    """Name for a candidate replacement parent playbook, timestamped for sequencing."""
    when = at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return f"[REFACTOR-M] {main_playbook_name} [at {when.isoformat(timespec='minutes')}]"


def _max_numeric_task_id(tasks: Mapping[str, Any]) -> int:
    highest = 0
    for key in tasks:
        try:
            highest = max(highest, int(str(key)))
        except ValueError:
            continue
    return highest


def _unused_task_id(tasks: Mapping[str, Any], preferred: str = "0") -> str:
    if preferred not in tasks:
        return preferred
    return str(_max_numeric_task_id(tasks) + 1)


def _start_task_node(start_id: str, first_task_id: str, position: Tuple[float, float]) -> JsonDict:
    inner_id = new_uuid()
    x, y = position
    return {
        "id": start_id,
        "taskId": inner_id,
        "type": "start",
        "task": {
            "id": inner_id,
            "version": -1,
            "name": "",
            "isCommand": False,
            "brand": "",
            "type": "start",
        },
        "nextTasks": {"#none#": [first_task_id]},
        "separateContext": False,
        "continueOnErrorType": "",
        "view": {"position": {"x": x, "y": y}},
        "note": False,
        "timerTriggers": [],
        "ignoreWorker": False,
        "skipUnavailable": False,
        "quietMode": 0,
        "isOverSize": False,
        "isAutoSwitchedToQuietMode": False,
    }


def _playbook_call_task(
    task_id: str,
    playbook_name: str,
    position: Tuple[float, float],
    *,
    display_name: Optional[str] = None,
    playbook_id: Optional[str] = None,
) -> JsonDict:
    inner_id = new_uuid()
    x, y = position
    inner: JsonDict = {
        "id": inner_id,
        "version": -1,
        "name": display_name or playbook_name,
        "type": "playbook",
        "isCommand": False,
        "brand": "",
    }
    if playbook_id:
        inner["playbookId"] = playbook_id
    else:
        inner["playbookName"] = playbook_name
    return {
        "id": task_id,
        "taskId": inner_id,
        "type": "playbook",
        "task": inner,
        # false = share parent/incident context (UI: "Share context").
        "separateContext": False,
        "continueOnErrorType": "",
        "loop": {
            "isCommand": False,
            "exitCondition": "",
            "wait": 1,
            "max": 0,
        },
        "view": {"position": {"x": x, "y": y}},
        "note": False,
        "timerTriggers": [],
        "ignoreWorker": False,
        "skipUnavailable": False,
        "quietMode": 0,
        "isOverSize": False,
        "isAutoSwitchedToQuietMode": False,
    }


def bounding_box(playbook: Mapping[str, Any], task_ids: Iterable[str]) -> Optional[Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    tasks = playbook_tasks(playbook)
    for tid in task_ids:
        node = tasks.get(str(tid))
        if not node:
            continue
        pos = task_position(node)
        if pos is None:
            continue
        xs.append(pos[0])
        ys.append(pos[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def shift_tasks(playbook: JsonDict, task_ids: Iterable[str], dx: float, dy: float) -> None:
    wanted = {str(t) for t in task_ids}
    tasks = playbook_tasks(playbook)
    for tid in wanted:
        node = tasks.get(tid)
        if not node:
            continue
        pos = task_position(node)
        if pos is None:
            continue
        set_task_position(node, pos[0] + dx, pos[1] + dy)


def auto_shift_right(
    playbook: JsonDict,
    task_ids: Sequence[str],
    *,
    padding: float = DEFAULT_VIEW_PADDING,
) -> Tuple[float, float]:
    """Move task_ids into empty space to the right of every other task. Return (dx, dy)."""
    shift_set = {str(t) for t in task_ids}
    box = bounding_box(playbook, shift_set)
    if box is None:
        return 0.0, 0.0
    min_x, _min_y, _max_x, _max_y = box
    other_ids = [tid for tid in playbook_tasks(playbook) if tid not in shift_set]
    other_box = bounding_box(playbook, other_ids)
    all_box = bounding_box(playbook, playbook_tasks(playbook).keys())
    right_edge = min_x
    if other_box:
        right_edge = max(right_edge, other_box[2])
    if all_box:
        right_edge = max(right_edge, all_box[2])
    dx = (right_edge + padding) - min_x
    if dx < padding:
        dx = padding
    shift_tasks(playbook, shift_set, dx, 0.0)
    _expand_paper(playbook)
    return dx, 0.0


def _expand_paper(playbook: JsonDict) -> None:
    box = bounding_box(playbook, playbook_tasks(playbook).keys())
    if box is None:
        return
    min_x, min_y, max_x, max_y = box
    as_string = isinstance(playbook.get("view"), str)
    view = parse_view(playbook.get("view")) or {}
    paper = dict(view.get("paper") or {})
    dimensions = dict(paper.get("dimensions") or {})
    dimensions["x"] = min_x - 50
    dimensions["y"] = min_y - 50
    dimensions["width"] = max(float(dimensions.get("width") or 0), (max_x - min_x) + 400)
    dimensions["height"] = max(float(dimensions.get("height") or 0), (max_y - min_y) + 400)
    paper["dimensions"] = dimensions
    view["paper"] = paper
    if "linkLabelsPosition" not in view:
        view["linkLabelsPosition"] = {}
    playbook["view"] = json.dumps(view, indent=4) if as_string else view


def _strip_successors_outside_cluster(node: JsonDict, cluster_ids: Set[str]) -> None:
    mapping = next_tasks_map(node)
    if not mapping:
        return
    rewritten: Dict[str, List[str]] = {}
    for label, targets in mapping.items():
        kept = [target for target in targets if target in cluster_ids]
        if kept:
            rewritten[label] = kept
    if rewritten:
        set_canonical(node, "nextTasks", rewritten)
    else:
        pop_field(node, "nextTasks")


def build_subplaybook_cluster(
    playbook: Mapping[str, Any],
    cluster_check: ClusterExtractCheckResult,
    *,
    name: str,
    playbook_id: Optional[str] = None,
    policy: Optional[FieldPolicy] = None,
) -> JsonDict:
    """Copy a start/end task cluster into a new playbook with a synthetic start task."""
    del policy
    pb = normalize_playbook(playbook)
    tasks = playbook_tasks(pb)
    cluster_ids = {str(tid) for tid in cluster_check.cluster_task_ids}
    start = cluster_check.start_task_id
    if start not in tasks:
        raise KeyError(f"Start task {start!r} does not exist")

    copied_tasks: JsonDict = {}
    for tid in cluster_check.cluster_task_ids:
        copied_tasks[tid] = copy.deepcopy(tasks[tid])
        _strip_successors_outside_cluster(copied_tasks[tid], cluster_ids)

    start_node = copied_tasks[start]
    start_id: str
    if task_type(start_node) != "start":
        start_id = _unused_task_id(copied_tasks, "0")
        pos = task_position(start_node) or DEFAULT_START_POSITION
        start_pos = (pos[0], pos[1] - 150)
        copied_tasks[start_id] = _start_task_node(start_id, start, start_pos)
    else:
        start_id = start

    sub: JsonDict = {
        "id": playbook_id or new_uuid(),
        "version": -1,
        "name": name,
        "startTaskId": start_id,
        "tasks": copied_tasks,
        "inputs": [],
        "outputs": [],
        "quiet": bool(pb.get("quiet") or False),
        "separateContext": True,
    }
    src_view = parse_view(pb.get("view"))
    if src_view:
        sub["view"] = copy.deepcopy(src_view)
    _expand_paper(sub)
    return sub


def build_subplaybook(
    playbook: Mapping[str, Any],
    task_id: str,
    *,
    name: str,
    playbook_id: Optional[str] = None,
    policy: Optional[FieldPolicy] = None,
    root_check: Optional[PotentialRootResult] = None,
) -> JsonDict:
    """Copy task + descendants into a new playbook with a synthetic start task."""
    del policy  # reserved: upload policy is applied later in yaml_codec
    pb = normalize_playbook(playbook)
    root = str(task_id)
    tasks = playbook_tasks(pb)
    if root not in tasks:
        raise KeyError(f"Task {root!r} does not exist")

    if root_check is not None:
        ids = list(root_check.descendant_ids)
    else:
        check = check_potential_root(pb, root)
        ids = list(check.descendant_ids)
    copied_tasks: JsonDict = {}
    for tid in ids:
        copied_tasks[tid] = copy.deepcopy(tasks[tid])

    root_node = copied_tasks[root]
    start_id: Optional[str] = None
    if task_type(root_node) != "start":
        start_id = _unused_task_id(copied_tasks, "0")
        pos = task_position(root_node) or DEFAULT_START_POSITION
        start_pos = (pos[0], pos[1] - 150)
        copied_tasks[start_id] = _start_task_node(start_id, root, start_pos)
    else:
        start_id = root

    sub: JsonDict = {
        "id": playbook_id or new_uuid(),
        "version": -1,
        "name": name,
        "startTaskId": start_id,
        "tasks": copied_tasks,
        "inputs": [],
        "outputs": [],
        "quiet": bool(pb.get("quiet") or False),
        # Playbook-level share-context. yaml_codec emits `separatecontext: true`.
        "separateContext": True,
    }
    src_view = parse_view(pb.get("view"))
    if src_view:
        sub["view"] = copy.deepcopy(src_view)
    _expand_paper(sub)
    return sub


def retarget_next_tasks(node: JsonDict, old_id: str, new_id: str) -> int:
    """Replace successor references from old_id to new_id. Return replacement count."""
    mapping = next_tasks_map(node)
    if not mapping:
        return 0
    changed = 0
    rewritten: Dict[str, List[str]] = {}
    for label, targets in mapping.items():
        new_targets = []
        for target in targets:
            if target == old_id:
                new_targets.append(new_id)
                changed += 1
            else:
                new_targets.append(target)
        rewritten[label] = new_targets
    if changed:
        set_canonical(node, "nextTasks", rewritten)
    return changed


def retarget_all_successors(playbook: Mapping[str, Any], old_id: str, new_id: str) -> int:
    """Retarget every nextTasks reference to old_id anywhere in the playbook."""
    if old_id == new_id:
        return 0
    replacements = 0
    for source_id, node in playbook_tasks(playbook).items():
        if source_id == new_id:
            continue
        replacements += retarget_next_tasks(node, old_id, new_id)
    return replacements


def rewrite_parent(
    playbook: Mapping[str, Any],
    task_id: str,
    *,
    subplaybook_name: str,
    subplaybook_id: Optional[str] = None,
    copy_name: str,
    copy_id: Optional[str] = None,
    padding: float = DEFAULT_VIEW_PADDING,
    root_check: Optional[PotentialRootResult] = None,
) -> JsonDict:
    """Copy the parent playbook, insert a leaf sub-playbook node, remove the extracted subgraph."""
    pb = normalize_playbook(copy.deepcopy(playbook))
    root = str(task_id)
    check = root_check or check_potential_root(pb, root)
    if not check.ok:
        raise ValueError("Cannot rewrite parent unless the task is a potential root: " + "; ".join(check.reasons))

    tasks = playbook_tasks(pb)
    root_node = tasks[root]
    pos = task_position(root_node) or DEFAULT_START_POSITION
    new_task_id = str(_max_numeric_task_id(tasks) + 1)
    call_node = _playbook_call_task(
        new_task_id,
        subplaybook_name,
        pos,
        playbook_id=subplaybook_id,
    )
    tasks[new_task_id] = call_node
    pb["tasks"] = tasks

    replacements = retarget_all_successors(pb, root, new_task_id)

    removed_ids = [tid for tid in check.descendant_ids if tid in tasks]
    for tid in removed_ids:
        del tasks[tid]
    pb["tasks"] = tasks
    _expand_paper(pb)

    original_id = str(playbook.get("id") or "")
    pb["id"] = copy_id or new_uuid()
    pb["name"] = copy_name
    pb["version"] = -1
    if original_id:
        pb["sourcePlaybookID"] = original_id
    pb["_refactor"] = {
        "kind": "root",
        "original_task_id": root,
        "subplaybook_task_id": new_task_id,
        "subplaybook_name": subplaybook_name,
        "subplaybook_id": subplaybook_id,
        "incoming_replacements": replacements,
        "removed_task_ids": removed_ids,
    }
    return pb


def rewrite_parent_cluster(
    playbook: Mapping[str, Any],
    cluster_check: ClusterExtractCheckResult,
    *,
    subplaybook_name: str,
    subplaybook_id: Optional[str] = None,
    copy_name: str,
    copy_id: Optional[str] = None,
    padding: float = DEFAULT_VIEW_PADDING,
) -> JsonDict:
    """Replace a start/end cluster with one sub-playbook call node."""
    del padding
    if not cluster_check.ok:
        raise ValueError(
            "Cannot rewrite parent unless the cluster is valid: " + "; ".join(cluster_check.reasons)
        )

    pb = normalize_playbook(copy.deepcopy(playbook))
    tasks = playbook_tasks(pb)
    start = cluster_check.start_task_id
    end = cluster_check.end_task_id
    cluster_ids = set(cluster_check.cluster_task_ids)

    start_node = tasks[start]
    pos = task_position(start_node) or DEFAULT_START_POSITION
    new_task_id = str(_max_numeric_task_id(tasks) + 1)
    call_node = _playbook_call_task(
        new_task_id,
        subplaybook_name,
        pos,
        playbook_id=subplaybook_id,
    )

    end_outgoing: Dict[str, List[str]] = {}
    for edge in cluster_check.end_outgoing:
        end_outgoing.setdefault(edge.label, []).append(edge.target_id)
    if end_outgoing:
        set_canonical(call_node, "nextTasks", end_outgoing)

    tasks[new_task_id] = call_node
    pb["tasks"] = tasks

    replacements = 0
    for edge in cluster_check.incoming_to_start:
        source = tasks.get(edge.source_id)
        if source:
            replacements += retarget_next_tasks(source, start, new_task_id)

    removed_ids = [tid for tid in cluster_check.cluster_task_ids if tid in tasks]
    for tid in removed_ids:
        del tasks[tid]
    pb["tasks"] = tasks
    _expand_paper(pb)

    original_id = str(playbook.get("id") or "")
    pb["id"] = copy_id or new_uuid()
    pb["name"] = copy_name
    pb["version"] = -1
    if original_id:
        pb["sourcePlaybookID"] = original_id
    pb["_refactor"] = {
        "kind": "cluster",
        "start_task_id": start,
        "end_task_id": end,
        "cluster_task_ids": list(cluster_check.cluster_task_ids),
        "subplaybook_task_id": new_task_id,
        "subplaybook_name": subplaybook_name,
        "subplaybook_id": subplaybook_id,
        "incoming_replacements": replacements,
        "removed_task_ids": removed_ids,
        "end_outgoing": [
            {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
            for e in cluster_check.end_outgoing
        ],
    }
    return pb


def rewrite_parent_multi(
    playbook: Mapping[str, Any],
    task_ids: Sequence[str],
    *,
    subplaybook_names: Sequence[str],
    subplaybook_ids: Optional[Sequence[Optional[str]]] = None,
    copy_name: str,
    copy_id: Optional[str] = None,
    padding: float = DEFAULT_VIEW_PADDING,
    root_checks: Optional[Sequence[PotentialRootResult]] = None,
) -> JsonDict:
    """Apply several extractions in sequence on one parent copy."""
    ordered_tasks = [str(task_id) for task_id in task_ids]
    ordered_names = [str(name) for name in subplaybook_names]
    if len(ordered_tasks) != len(ordered_names):
        raise ValueError("task_ids and subplaybook_names must have the same length")
    ordered_ids: List[Optional[str]]
    if subplaybook_ids is None:
        ordered_ids = [None] * len(ordered_tasks)
    else:
        ordered_ids = [str(item) if item else None for item in subplaybook_ids]
        if len(ordered_ids) != len(ordered_tasks):
            raise ValueError("subplaybook_ids length must match task_ids")

    checks = list(root_checks or [])
    if not checks:
        checks = [check_potential_root(playbook, task_id) for task_id in ordered_tasks]
    if len(checks) != len(ordered_tasks):
        raise ValueError("root_checks length must match task_ids")

    current = normalize_playbook(copy.deepcopy(playbook))
    extractions: List[JsonDict] = []
    current_copy_id = copy_id
    for task_id, sub_name, sub_id, root_check in zip(ordered_tasks, ordered_names, ordered_ids, checks):
        current = rewrite_parent(
            current,
            task_id,
            subplaybook_name=sub_name,
            subplaybook_id=sub_id,
            copy_name=copy_name,
            copy_id=current_copy_id,
            padding=padding,
            root_check=root_check,
        )
        meta = dict(current.get("_refactor") or {})
        extractions.append(meta)
        current_copy_id = str(current.get("id") or current_copy_id or "")

    current["_refactor"] = {
        "extractions": extractions,
        "task_ids": ordered_tasks,
        "subplaybook_names": ordered_names,
        "subplaybook_ids": ordered_ids,
    }
    return current


def rewrite_parent_combined(
    playbook: Mapping[str, Any],
    *,
    cluster_checks: Sequence[ClusterExtractCheckResult],
    cluster_subplaybook_names: Sequence[str],
    cluster_subplaybook_ids: Optional[Sequence[Optional[str]]] = None,
    task_ids: Sequence[str],
    subplaybook_names: Sequence[str],
    subplaybook_ids: Optional[Sequence[Optional[str]]] = None,
    copy_name: str,
    copy_id: Optional[str] = None,
    padding: float = DEFAULT_VIEW_PADDING,
    root_checks: Optional[Sequence[PotentialRootResult]] = None,
) -> JsonDict:
    """Apply cluster extractions first, then potential-root extractions on one parent copy."""
    ordered_clusters = list(cluster_checks)
    ordered_cluster_names = [str(name) for name in cluster_subplaybook_names]
    if len(ordered_clusters) != len(ordered_cluster_names):
        raise ValueError("cluster_checks and cluster_subplaybook_names must have the same length")
    ordered_cluster_ids: List[Optional[str]]
    if cluster_subplaybook_ids is None:
        ordered_cluster_ids = [None] * len(ordered_clusters)
    else:
        ordered_cluster_ids = [str(item) if item else None for item in cluster_subplaybook_ids]
        if len(ordered_cluster_ids) != len(ordered_clusters):
            raise ValueError("cluster_subplaybook_ids length must match cluster_checks")

    current = normalize_playbook(copy.deepcopy(playbook))
    extractions: List[JsonDict] = []
    current_copy_id = copy_id
    for cluster_check, sub_name, sub_id in zip(
        ordered_clusters, ordered_cluster_names, ordered_cluster_ids
    ):
        current = rewrite_parent_cluster(
            current,
            cluster_check,
            subplaybook_name=sub_name,
            subplaybook_id=sub_id,
            copy_name=copy_name,
            copy_id=current_copy_id,
            padding=padding,
        )
        meta = dict(current.get("_refactor") or {})
        extractions.append(meta)
        current_copy_id = str(current.get("id") or current_copy_id or "")

    current = rewrite_parent_multi(
        current,
        task_ids,
        subplaybook_names=subplaybook_names,
        subplaybook_ids=subplaybook_ids,
        copy_name=copy_name,
        copy_id=current_copy_id,
        padding=padding,
        root_checks=root_checks,
    )
    root_meta = dict(current.get("_refactor") or {})
    root_meta["cluster_extractions"] = extractions
    current["_refactor"] = root_meta
    return current
