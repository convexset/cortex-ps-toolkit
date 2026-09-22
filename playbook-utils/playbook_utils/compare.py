"""Canonical traversal and subgraph equality (check B)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:
    from .cache import PlaybookCache

from .fields import FieldPolicy, strip_ignored
from .graph import incoming_edges
from .keys import (
    JsonDict,
    align_playbook_fields_for_compare,
    align_script_fields_for_compare,
    drop_compare_defaults,
    inner_task,
    iter_successors,
    next_tasks_map,
    normalize_playbook,
    playbook_tasks,
    rename_known_keys_to_canonical,
    successor_ids,
    task_name,
    task_type,
)


@dataclass
class CanonicalNode:
    index: int
    orig_id: str
    type: str
    name: str
    next_tasks: Dict[str, List[int]]
    payload: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "index": self.index,
            "orig_id": self.orig_id,
            "type": self.type,
            "name": self.name,
            "nextTasks": self.next_tasks,
            "payload": self.payload,
        }

    def comparable(self) -> JsonDict:
        return {
            "type": self.type,
            "name": self.name,
            "nextTasks": self.next_tasks,
            "payload": self.payload,
        }


@dataclass
class CanonicalGraph:
    root_orig_id: str
    skipped_start_id: Optional[str]
    nodes: List[CanonicalNode]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "root_orig_id": self.root_orig_id,
            "skipped_start_id": self.skipped_start_id,
            "warnings": list(self.warnings),
            "nodes": [node.to_dict() for node in self.nodes],
        }

    def comparable_nodes(self) -> List[JsonDict]:
        return [node.comparable() for node in self.nodes]


@dataclass
class PathDiff:
    path: str
    left: Any
    right: Any

    def to_dict(self) -> JsonDict:
        return {"path": self.path, "left": self.left, "right": self.right}


@dataclass
class CompareResult:
    equal: bool
    left_root: str
    right_root: str
    left_count: int
    right_count: int
    diffs: List[PathDiff]
    left: CanonicalGraph
    right: CanonicalGraph

    def to_dict(self) -> JsonDict:
        return {
            "equal": self.equal,
            "left_root": self.left_root,
            "right_root": self.right_root,
            "left_count": self.left_count,
            "right_count": self.right_count,
            "diffs": [d.to_dict() for d in self.diffs],
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    def human_summary(self) -> str:
        lines = [
            f"equal: {self.equal}",
            f"left root: {self.left_root} ({self.left_count} nodes)",
            f"right root: {self.right_root} ({self.right_count} nodes)",
        ]
        if self.left.skipped_start_id:
            lines.append(f"left skipped start: {self.left.skipped_start_id}")
        if self.right.skipped_start_id:
            lines.append(f"right skipped start: {self.right.skipped_start_id}")
        if not self.diffs:
            return "\n".join(lines)
        counts = summarize_diff_paths(self.diffs)
        lines.append(f"diffs: {len(self.diffs)}")
        lines.append("diff counts by relative path:")
        for path, count in counts["by_relative_path"].items():
            lines.append(f"  {count:4d}  {path}")
        lines.append("all diffs:")
        for diff in self.diffs:
            task_id = task_id_for_diff_path(diff.path, self.left)
            task_label = f"task {task_id} " if task_id else ""
            lines.append(f"  {task_label}{diff.path}: {diff.left!r} != {diff.right!r}")
        return "\n".join(lines)


_NODE_PREFIX = re.compile(r"^nodes\[\d+\]\.?")
_NODE_INDEX = re.compile(r"^nodes\[(\d+)\]")


def relative_diff_path(path: str) -> str:
    """Strip `nodes[i].` so the same field across tasks can be counted together."""
    stripped = _NODE_PREFIX.sub("", path)
    return stripped or path


def task_id_for_diff_path(path: str, graph: CanonicalGraph) -> Optional[str]:
    match = _NODE_INDEX.match(path)
    if not match:
        return None
    index = int(match.group(1))
    if index < 0 or index >= len(graph.nodes):
        return None
    return str(graph.nodes[index].orig_id)


def format_compare_log_line(compared: CompareResult, label: str) -> str:
    """One-line compare summary for refactor logs (task ids + diff keys)."""
    if compared.equal:
        return f"Compare {label}: equal=True diffs=0"
    summary = summarize_diff_paths(compared.diffs)
    task_ids: List[str] = []
    for diff in compared.diffs:
        task_id = task_id_for_diff_path(diff.path, compared.left)
        if task_id and task_id not in task_ids:
            task_ids.append(task_id)

    def _sort_key(task_id: str) -> tuple[int, int | str]:
        if task_id.isdigit():
            return (0, int(task_id))
        return (1, task_id)

    task_ids.sort(key=_sort_key)
    leaf_keys = list(summary.get("by_leaf_key") or {})
    rel_paths = list((summary.get("by_relative_path") or {}).keys())
    parts = [f"Compare {label}: equal=False diffs={len(compared.diffs)}"]
    if task_ids:
        parts.append(f"tasks={','.join(task_ids)}")
    if leaf_keys:
        parts.append(f"keys={','.join(leaf_keys)}")
    if rel_paths:
        parts.append(f"paths={','.join(rel_paths)}")
    return " ".join(parts)


def summarize_diff_paths(diffs: Sequence[PathDiff]) -> JsonDict:
    """Count diffs by relative path and by leaf key (for include/exclude decisions)."""
    by_relative: Dict[str, int] = {}
    by_leaf: Dict[str, int] = {}
    for diff in diffs:
        rel = relative_diff_path(diff.path)
        leaf = rel.rsplit(".", 1)[-1] if rel else diff.path
        by_relative[rel] = by_relative.get(rel, 0) + 1
        by_leaf[leaf] = by_leaf.get(leaf, 0) + 1
    return {
        "by_relative_path": dict(sorted(by_relative.items(), key=lambda item: (-item[1], item[0]))),
        "by_leaf_key": dict(sorted(by_leaf.items(), key=lambda item: (-item[1], item[0]))),
    }


def unfiltered_field_policy() -> FieldPolicy:
    """Compare with no ignore keys — every payload field difference is reported."""
    return FieldPolicy(compare_ignore_keys=())


def effective_root_id(
    playbook: Mapping[str, object],
    task_id: str,
    *,
    skip_start: Optional[bool] = None,
) -> Tuple[str, Optional[str], List[str]]:
    """Return (compare_root, skipped_start_id, warnings)."""
    pb = normalize_playbook(playbook)
    tasks = playbook_tasks(pb)
    tid = str(task_id)
    warnings: List[str] = []
    if tid not in tasks:
        raise KeyError(f"Task {tid!r} does not exist")
    node = tasks[tid]
    should_skip = task_type(node) == "start" if skip_start is None else skip_start
    if not should_skip or task_type(node) != "start":
        return tid, None, warnings
    succs = successor_ids(node)
    unique = []
    seen: Set[str] = set()
    for sid in succs:
        if sid not in seen:
            seen.add(sid)
            unique.append(sid)
    if not unique:
        warnings.append(f"Start task {tid!r} has no successors; comparing the start node")
        return tid, None, warnings
    if len(unique) > 1:
        warnings.append(
            f"Start task {tid!r} has {len(unique)} successors {unique}; using first {unique[0]!r}"
        )
    return unique[0], tid, warnings


def canonicalize(
    playbook: Mapping[str, object],
    task_id: str,
    *,
    policy: Optional[FieldPolicy] = None,
    skip_start: Optional[bool] = None,
) -> CanonicalGraph:
    """Linearize the subgraph from a potential root, rewriting edges to canonical indices."""
    policy = policy or FieldPolicy()
    ignore = policy.ignore_set()
    pb = normalize_playbook(playbook)
    tasks = playbook_tasks(pb)
    root_id, skipped_start, warnings = effective_root_id(pb, task_id, skip_start=skip_start)
    if root_id not in tasks:
        raise KeyError(f"Task {root_id!r} does not exist")

    index_by_orig: Dict[str, int] = {}
    nodes: List[CanonicalNode] = []

    def visit(orig_id: str) -> int:
        if orig_id in index_by_orig:
            return index_by_orig[orig_id]
        node = tasks.get(orig_id)
        if node is None:
            raise KeyError(f"Dangling nextTasks reference to {orig_id!r}")
        idx = len(nodes)
        index_by_orig[orig_id] = idx
        # Placeholder so children can refer to this index on back-edges.
        nodes.append(
            CanonicalNode(
                index=idx,
                orig_id=orig_id,
                type=task_type(node),
                name=task_name(node),
                next_tasks={},
                payload={},
            )
        )
        rewritten: Dict[str, List[int]] = {}
        mapping = next_tasks_map(node)
        for label in sorted(mapping.keys()):
            rewritten[label] = [visit(target) for target in mapping[label]]
        payload = strip_ignored(_node_payload(node), ignore)
        nodes[idx] = CanonicalNode(
            index=idx,
            orig_id=orig_id,
            type=task_type(node),
            name=task_name(node),
            next_tasks=rewritten,
            payload=payload,
        )
        return idx

    visit(root_id)
    return CanonicalGraph(
        root_orig_id=root_id,
        skipped_start_id=skipped_start,
        nodes=nodes,
        warnings=warnings,
    )


def _task_sort_key(task_id: str) -> Tuple[int, str]:
    return (0, f"{int(task_id):020d}") if str(task_id).isdigit() else (1, str(task_id))


def canonicalize_extract_tasks(
    playbook: Mapping[str, object],
    compare_root_id: str,
    allowed_task_ids: Set[str],
    *,
    policy: Optional[FieldPolicy] = None,
    skip_start: Optional[bool] = None,
) -> CanonicalGraph:
    """Linearize an extracted task set that may include disconnected orphan feeders."""
    policy = policy or FieldPolicy()
    ignore = policy.ignore_set()
    pb = normalize_playbook(playbook)
    tasks = playbook_tasks(pb)
    allowed = {str(task_id) for task_id in allowed_task_ids}
    root_id, skipped_start, warnings = effective_root_id(pb, compare_root_id, skip_start=skip_start)
    if root_id not in allowed:
        raise KeyError(f"Root task {root_id!r} is not in the allowed task set")

    index_by_orig: Dict[str, int] = {}
    nodes: List[CanonicalNode] = []

    def visit(orig_id: str) -> int:
        if orig_id not in allowed:
            raise KeyError(f"Edge leaves allowed task set at {orig_id!r}")
        if orig_id in index_by_orig:
            return index_by_orig[orig_id]
        node = tasks.get(orig_id)
        if node is None:
            raise KeyError(f"Dangling nextTasks reference to {orig_id!r}")
        idx = len(nodes)
        index_by_orig[orig_id] = idx
        nodes.append(
            CanonicalNode(
                index=idx,
                orig_id=orig_id,
                type=task_type(node),
                name=task_name(node),
                next_tasks={},
                payload={},
            )
        )
        rewritten: Dict[str, List[int]] = {}
        mapping = next_tasks_map(node)
        for label in sorted(mapping.keys()):
            rewritten[label] = [visit(target) for target in mapping[label] if target in allowed]
        payload = strip_ignored(_node_payload(node), ignore)
        nodes[idx] = CanonicalNode(
            index=idx,
            orig_id=orig_id,
            type=task_type(node),
            name=task_name(node),
            next_tasks=rewritten,
            payload=payload,
        )
        return idx

    entries = [
        tid
        for tid in allowed
        if not any(edge.source_id in allowed for edge in incoming_edges(pb, [tid]))
    ]
    entries.sort(key=lambda tid: (tid == root_id, _task_sort_key(tid)))
    for entry_id in entries:
        if entry_id not in index_by_orig:
            visit(entry_id)
    for tid in sorted(allowed, key=_task_sort_key):
        if tid not in index_by_orig:
            visit(tid)

    return CanonicalGraph(
        root_orig_id=root_id,
        skipped_start_id=skipped_start,
        nodes=nodes,
        warnings=warnings,
    )


def _node_payload(node: Mapping[str, object]) -> JsonDict:
    """Task content without nextTasks (structure is stored separately)."""
    payload = dict(node)
    payload.pop("nextTasks", None)
    payload.pop("nexttasks", None)
    inner = inner_task(payload)
    if inner:
        payload["task"] = dict(inner)
        align_script_fields_for_compare(payload["task"])
        align_playbook_fields_for_compare(payload["task"])
    payload = rename_known_keys_to_canonical(payload)
    inner = payload.get("task")
    if isinstance(inner, dict):
        align_script_fields_for_compare(inner)
        align_playbook_fields_for_compare(inner)
    return drop_compare_defaults(payload)


def _diff_values(left: Any, right: Any, path: str, diffs: List[PathDiff]) -> None:
    if type(left) is not type(right) and not (
        isinstance(left, (int, float)) and isinstance(right, (int, float))
    ):
        diffs.append(PathDiff(path=path or "$", left=left, right=right))
        return
    if isinstance(left, dict) and isinstance(right, dict):
        keys = sorted(set(left) | set(right), key=str)
        for key in keys:
            child = f"{path}.{key}" if path else str(key)
            if key not in left:
                diffs.append(PathDiff(path=child, left=None, right=right[key]))
            elif key not in right:
                diffs.append(PathDiff(path=child, left=left[key], right=None))
            else:
                _diff_values(left[key], right[key], child, diffs)
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            diffs.append(PathDiff(path=f"{path}.length", left=len(left), right=len(right)))
        for i, (lv, rv) in enumerate(zip(left, right)):
            _diff_values(lv, rv, f"{path}[{i}]", diffs)
        return
    if left != right:
        diffs.append(PathDiff(path=path or "$", left=left, right=right))


def compare_potential_roots(
    left_playbook: Mapping[str, object],
    left_task_id: str,
    right_playbook: Mapping[str, object],
    right_task_id: str,
    *,
    policy: Optional[FieldPolicy] = None,
    skip_start_left: Optional[bool] = None,
    skip_start_right: Optional[bool] = None,
) -> CompareResult:
    """Compare two potential-root subgraphs after canonical linearization."""
    policy = policy or FieldPolicy()
    left = canonicalize(left_playbook, left_task_id, policy=policy, skip_start=skip_start_left)
    right = canonicalize(right_playbook, right_task_id, policy=policy, skip_start=skip_start_right)
    diffs: List[PathDiff] = []
    if len(left.nodes) != len(right.nodes):
        diffs.append(
            PathDiff(path="node_count", left=len(left.nodes), right=len(right.nodes))
        )
    for i, (ln, rn) in enumerate(zip(left.nodes, right.nodes)):
        _diff_values(ln.comparable(), rn.comparable(), f"nodes[{i}]", diffs)
    return CompareResult(
        equal=not diffs,
        left_root=left.root_orig_id,
        right_root=right.root_orig_id,
        left_count=len(left.nodes),
        right_count=len(right.nodes),
        diffs=diffs,
        left=left,
        right=right,
    )


def compare_source_to_downloaded_subplaybook(
    source_playbook: Mapping[str, object],
    source_task_id: str,
    downloaded: Mapping[str, object],
    *,
    policy: Optional[FieldPolicy] = None,
    allowed_task_ids: Optional[Set[str]] = None,
    cache: Optional["PlaybookCache"] = None,
) -> CompareResult:
    """Compare extracted source subgraph to a downloaded sub-playbook (skip its start)."""
    import copy

    from .bindings import inherit_playbook_bindings_from_source, normalize_playbook_call_ids_for_compare
    from .graph import check_potential_root
    from .keys import start_task_id

    downloaded_copy = normalize_playbook(copy.deepcopy(downloaded))
    if allowed_task_ids is None:
        allowed_task_ids = set(check_potential_root(source_playbook, source_task_id).descendant_ids)
    inherit_playbook_bindings_from_source(downloaded_copy, source_playbook, task_ids=allowed_task_ids)
    source_copy = normalize_playbook(copy.deepcopy(source_playbook))
    if cache is not None:
        from .bindings import id_to_name_map, name_to_id_map

        name_to_id = name_to_id_map(cache)
        id_to_name = id_to_name_map(cache)
        normalize_playbook_call_ids_for_compare(
            source_copy,
            name_to_id=name_to_id,
            id_to_name=id_to_name,
            task_ids=allowed_task_ids,
        )
        normalize_playbook_call_ids_for_compare(
            downloaded_copy,
            name_to_id=name_to_id,
            id_to_name=id_to_name,
            task_ids=allowed_task_ids,
        )
    start = start_task_id(downloaded_copy) or source_task_id
    policy = policy or FieldPolicy()
    left = canonicalize_extract_tasks(
        source_copy,
        source_task_id,
        allowed_task_ids,
        policy=policy,
        skip_start=False,
    )
    right = canonicalize_extract_tasks(
        downloaded_copy,
        start,
        allowed_task_ids,
        policy=policy,
        skip_start=True,
    )
    diffs: List[PathDiff] = []
    if len(left.nodes) != len(right.nodes):
        diffs.append(PathDiff(path="node_count", left=len(left.nodes), right=len(right.nodes)))
    for i, (ln, rn) in enumerate(zip(left.nodes, right.nodes)):
        _diff_values(ln.comparable(), rn.comparable(), f"nodes[{i}]", diffs)
    return CompareResult(
        equal=not diffs,
        left_root=left.root_orig_id,
        right_root=right.root_orig_id,
        left_count=len(left.nodes),
        right_count=len(right.nodes),
        diffs=diffs,
        left=left,
        right=right,
    )


def canonicalize_task_set(
    playbook: Mapping[str, object],
    root_task_id: str,
    allowed_task_ids: Set[str],
    *,
    policy: Optional[FieldPolicy] = None,
    skip_start: Optional[bool] = None,
) -> CanonicalGraph:
    """Linearize a bounded subgraph that may only visit allowed task ids."""
    policy = policy or FieldPolicy()
    ignore = policy.ignore_set()
    pb = normalize_playbook(playbook)
    tasks = playbook_tasks(pb)
    allowed = {str(task_id) for task_id in allowed_task_ids}
    root_id, skipped_start, warnings = effective_root_id(pb, root_task_id, skip_start=skip_start)
    if root_id not in allowed:
        raise KeyError(f"Root task {root_id!r} is not in the allowed task set")

    index_by_orig: Dict[str, int] = {}
    nodes: List[CanonicalNode] = []

    def visit(orig_id: str) -> int:
        if orig_id not in allowed:
            raise KeyError(f"Edge leaves allowed task set at {orig_id!r}")
        if orig_id in index_by_orig:
            return index_by_orig[orig_id]
        node = tasks.get(orig_id)
        if node is None:
            raise KeyError(f"Dangling nextTasks reference to {orig_id!r}")
        idx = len(nodes)
        index_by_orig[orig_id] = idx
        nodes.append(
            CanonicalNode(
                index=idx,
                orig_id=orig_id,
                type=task_type(node),
                name=task_name(node),
                next_tasks={},
                payload={},
            )
        )
        rewritten: Dict[str, List[int]] = {}
        mapping = next_tasks_map(node)
        for label in sorted(mapping.keys()):
            rewritten[label] = [visit(target) for target in mapping[label] if target in allowed]
        payload = strip_ignored(_node_payload(node), ignore)
        nodes[idx] = CanonicalNode(
            index=idx,
            orig_id=orig_id,
            type=task_type(node),
            name=task_name(node),
            next_tasks=rewritten,
            payload=payload,
        )
        return idx

    visit(root_id)
    return CanonicalGraph(
        root_orig_id=root_id,
        skipped_start_id=skipped_start,
        nodes=nodes,
        warnings=warnings,
    )


def compare_source_to_downloaded_cluster_subplaybook(
    source_playbook: Mapping[str, object],
    cluster_check: Mapping[str, object],
    downloaded: Mapping[str, object],
    *,
    policy: Optional[FieldPolicy] = None,
    cache: Optional["PlaybookCache"] = None,
) -> CompareResult:
    """Compare an extracted source cluster to a downloaded sub-playbook (skip its start)."""
    import copy

    from .extract import _strip_successors_outside_cluster
    from .graph import ClusterExtractCheckResult
    from .keys import start_task_id

    if isinstance(cluster_check, ClusterExtractCheckResult):
        check = cluster_check
    else:
        check = ClusterExtractCheckResult(
            start_task_id=str(cluster_check["start_task_id"]),
            end_task_id=str(cluster_check["end_task_id"]),
            ok=bool(cluster_check.get("ok")),
            cluster_task_ids=[str(item) for item in cluster_check.get("cluster_task_ids") or []],
            orphan_feeder_ids=[str(item) for item in cluster_check.get("orphan_feeder_ids") or []],
            bypass_task_ids=[],
            outside_outgoing=[],
            outside_incoming=[],
            incoming_to_start=[],
            end_outgoing=[],
        )
    allowed = set(check.cluster_task_ids)
    source_copy = normalize_playbook(copy.deepcopy(source_playbook))
    source_tasks = playbook_tasks(source_copy)
    for tid in check.cluster_task_ids:
        node = source_tasks.get(tid)
        if isinstance(node, dict):
            _strip_successors_outside_cluster(node, allowed)
    start = start_task_id(downloaded) or check.start_task_id
    policy = policy or FieldPolicy()
    from .bindings import inherit_playbook_bindings_from_source, normalize_playbook_call_ids_for_compare

    downloaded_copy = normalize_playbook(copy.deepcopy(downloaded))
    inherit_playbook_bindings_from_source(downloaded_copy, source_copy, task_ids=allowed)
    if cache is not None:
        from .bindings import id_to_name_map, name_to_id_map

        name_to_id = name_to_id_map(cache)
        id_to_name = id_to_name_map(cache)
        normalize_playbook_call_ids_for_compare(
            source_copy,
            name_to_id=name_to_id,
            id_to_name=id_to_name,
            task_ids=allowed,
        )
        normalize_playbook_call_ids_for_compare(
            downloaded_copy,
            name_to_id=name_to_id,
            id_to_name=id_to_name,
            task_ids=allowed,
        )
    left = canonicalize_task_set(
        source_copy,
        check.start_task_id,
        allowed,
        policy=policy,
        skip_start=False,
    )
    right = canonicalize_task_set(
        downloaded_copy,
        start,
        allowed,
        policy=policy,
        skip_start=True,
    )
    diffs: List[PathDiff] = []
    if len(left.nodes) != len(right.nodes):
        diffs.append(PathDiff(path="node_count", left=len(left.nodes), right=len(right.nodes)))
    for i, (ln, rn) in enumerate(zip(left.nodes, right.nodes)):
        _diff_values(ln.comparable(), rn.comparable(), f"nodes[{i}]", diffs)
    return CompareResult(
        equal=not diffs,
        left_root=left.root_orig_id,
        right_root=right.root_orig_id,
        left_count=len(left.nodes),
        right_count=len(right.nodes),
        diffs=diffs,
        left=left,
        right=right,
    )
