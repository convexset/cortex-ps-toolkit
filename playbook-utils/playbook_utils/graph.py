"""Potential-root checks and descendant collection (check A)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .keys import (
    JsonDict,
    iter_successors,
    normalize_playbook,
    playbook_tasks,
    start_task_id,
    task_name,
    task_type,
)


@dataclass
class IncomingEdge:
    source_id: str
    label: str
    target_id: str


def _task_sort_key(task_id: str) -> Tuple[int, str]:
    return (0, f"{int(task_id):020d}") if str(task_id).isdigit() else (1, str(task_id))


def _orphan_outside_chain_from_source(
    playbook: Mapping[str, object],
    source_id: str,
    core_set: Set[str],
    start: str,
) -> Set[str]:
    """Outside-only chain ending at source_id when it is orphan-rooted; else empty."""
    if source_id in core_set or source_id == start:
        return set()

    chain: Set[str] = set()
    pending: List[str] = [source_id]
    waiting_on: Set[str] = set()
    task_count = len(playbook_tasks(playbook))
    max_steps = max(task_count * task_count, 1)
    steps = 0
    while pending:
        steps += 1
        if steps > max_steps:
            return set()
        tid = pending.pop(0)
        if tid in chain or tid in core_set or tid == start:
            continue
        incoming = incoming_edges(playbook, [tid])
        if any(edge.source_id == start for edge in incoming):
            return set()
        outside_incoming = [
            edge for edge in incoming if edge.source_id not in core_set and edge.source_id != start
        ]
        if not incoming:
            chain.add(tid)
            waiting_on.discard(tid)
            continue
        if not outside_incoming:
            return set()
        unresolved = [edge.source_id for edge in outside_incoming if edge.source_id not in chain]
        if unresolved:
            if tid in waiting_on:
                return set()
            waiting_on.add(tid)
            pending.extend(unresolved)
            pending.append(tid)
            continue
        waiting_on.discard(tid)
        chain.add(tid)

    if not chain:
        return set()
    if not any(not incoming_edges(playbook, [node]) for node in chain):
        return set()
    return chain


def orphan_feeders_for_leaks(
    playbook: Mapping[str, object],
    core_set: Set[str],
    leak_edges: Sequence[IncomingEdge],
) -> Set[str]:
    """Orphan-rooted outside chains that explain blocking outside incoming edges into core_set."""
    pb = normalize_playbook(playbook)
    start = start_task_id(pb)
    feeders: Set[str] = set()
    for leak in leak_edges:
        feeders |= _orphan_outside_chain_from_source(pb, leak.source_id, core_set, start)
    return feeders


def ordered_orphan_feeders(
    playbook: Mapping[str, object],
    core_set: Set[str],
    orphan_set: Set[str],
) -> List[str]:
    """Topologically order orphan feeders before their dependents."""
    if not orphan_set:
        return []
    pb = normalize_playbook(playbook)
    ordered: List[str] = []
    remaining = set(orphan_set)
    while remaining:
        ready = sorted(
            [
                tid
                for tid in remaining
                if not any(
                    edge.source_id in remaining
                    for edge in incoming_edges(pb, [tid], exclude_sources=core_set)
                )
            ],
            key=_task_sort_key,
        )
        if not ready:
            ready = sorted(remaining, key=_task_sort_key)
        for tid in ready:
            ordered.append(tid)
            remaining.remove(tid)
    return ordered


def extended_extract_task_ids(
    playbook: Mapping[str, object],
    core_descendants: Sequence[str],
    orphan_feeders: Set[str],
) -> List[str]:
    """Core descendants plus orphan feeders, orphans first in topo order."""
    pb = normalize_playbook(playbook)
    core_set = set(core_descendants)
    ordered: List[str] = []
    seen: Set[str] = set()
    for tid in ordered_orphan_feeders(pb, core_set, orphan_feeders):
        if tid not in seen:
            seen.add(tid)
            ordered.append(tid)
    for tid in core_descendants:
        if tid not in seen:
            seen.add(tid)
            ordered.append(tid)
    return ordered


@dataclass
class PotentialRootResult:
    task_id: str
    ok: bool
    exists: bool
    descendant_ids: List[str]
    orphan_feeder_ids: List[str]
    self_reachable: bool
    outside_incoming_to_descendants: List[IncomingEdge]
    incoming_to_root: List[IncomingEdge]
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "ok": self.ok,
            "exists": self.exists,
            "descendant_ids": list(self.descendant_ids),
            "orphan_feeder_ids": list(self.orphan_feeder_ids),
            "self_reachable": self.self_reachable,
            "outside_incoming_to_descendants": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.outside_incoming_to_descendants
            ],
            "incoming_to_root": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.incoming_to_root
            ],
            "reasons": list(self.reasons),
        }


def descendant_ids(playbook: Mapping[str, object], root_id: str) -> List[str]:
    """Task ids reachable from root_id including itself, BFS, first-seen order."""
    tasks = playbook_tasks(playbook)
    root = str(root_id)
    if root not in tasks:
        return []
    ordered: List[str] = []
    seen: Set[str] = set()
    queue: List[str] = [root]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        node = tasks.get(current)
        if not node:
            continue
        for _, target in iter_successors(node):
            if target not in seen:
                queue.append(target)
    return ordered


def total_successors(playbook: Mapping[str, object], task_id: str) -> List[str]:
    """Task ids reachable from task_id excluding itself, in descendant BFS order."""
    root = str(task_id)
    return [tid for tid in descendant_ids(playbook, root) if tid != root]


def _reaches_self(playbook: Mapping[str, object], root_id: str) -> bool:
    """True if a non-empty path from root returns to root."""
    tasks = playbook_tasks(playbook)
    root = str(root_id)
    node = tasks.get(root)
    if not node:
        return False
    start_from = [target for _, target in iter_successors(node)]
    seen: Set[str] = set()
    queue: List[str] = list(start_from)
    while queue:
        current = queue.pop(0)
        if current == root:
            return True
        if current in seen:
            continue
        seen.add(current)
        nxt = tasks.get(current)
        if not nxt:
            continue
        for _, target in iter_successors(nxt):
            if target not in seen or target == root:
                queue.append(target)
    return False


def incoming_edges(
    playbook: Mapping[str, object],
    target_ids: Iterable[str],
    *,
    exclude_sources: Optional[Iterable[str]] = None,
) -> List[IncomingEdge]:
    """Edges whose target is in target_ids and whose source is not excluded."""
    wanted = {str(t) for t in target_ids}
    skip = {str(s) for s in (exclude_sources or [])}
    edges: List[IncomingEdge] = []
    for source_id, node in playbook_tasks(playbook).items():
        if source_id in skip:
            continue
        for label, target in iter_successors(node):
            if target in wanted:
                edges.append(IncomingEdge(source_id=source_id, label=label, target_id=target))
    return edges


def check_potential_root(playbook: Mapping[str, object], task_id: str) -> PotentialRootResult:
    """A task is a potential root if it cannot reach itself and descendants have no outside in-edges except to the root."""
    pb = normalize_playbook(playbook)
    tid = str(task_id)
    tasks = playbook_tasks(pb)
    if tid not in tasks:
        return PotentialRootResult(
            task_id=tid,
            ok=False,
            exists=False,
            descendant_ids=[],
            orphan_feeder_ids=[],
            self_reachable=False,
            outside_incoming_to_descendants=[],
            incoming_to_root=[],
            reasons=[f"Task {tid!r} does not exist in playbook"],
        )

    core_descendants = descendant_ids(pb, tid)
    desc_set = set(core_descendants)
    self_reachable = _reaches_self(pb, tid)
    leaks = incoming_edges(pb, desc_set - {tid}, exclude_sources=desc_set)
    orphan_feeders = orphan_feeders_for_leaks(pb, desc_set, leaks)
    extended_descendants = extended_extract_task_ids(pb, core_descendants, orphan_feeders)
    allowed_leak_sources = orphan_feeders
    blocking_leaks = [edge for edge in leaks if edge.source_id not in allowed_leak_sources]
    to_root = incoming_edges(pb, [tid], exclude_sources=desc_set)

    reasons: List[str] = []
    if self_reachable:
        reasons.append(
            f"Task {tid!r} ({task_name(tasks[tid]) or task_type(tasks[tid])}) can reach itself via nextTasks"
        )
    for edge in blocking_leaks:
        reasons.append(
            f"Outside task {edge.source_id!r} --{edge.label}--> descendant {edge.target_id!r}"
        )

    return PotentialRootResult(
        task_id=tid,
        ok=not self_reachable and not blocking_leaks,
        exists=True,
        descendant_ids=extended_descendants,
        orphan_feeder_ids=ordered_orphan_feeders(pb, desc_set, orphan_feeders),
        self_reachable=self_reachable,
        outside_incoming_to_descendants=leaks,
        incoming_to_root=to_root,
        reasons=reasons,
    )


@dataclass
class MultiExtractCheckResult:
    task_ids: List[str]
    ok: bool
    root_checks: List[PotentialRootResult]
    sequence_conflicts: List[JsonDict]
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "task_ids": list(self.task_ids),
            "ok": self.ok,
            "root_checks": [item.to_dict() for item in self.root_checks],
            "sequence_conflicts": list(self.sequence_conflicts),
            "reasons": list(self.reasons),
        }


def check_multi_extract(playbook: Mapping[str, object], task_ids: Sequence[str]) -> MultiExtractCheckResult:
    """Validate a sequence of tasks for simultaneous refactor.

    Each task must be a potential root. No task in the set may be a successor of any
    other task in the set (pairwise: neither direction may hold).
    """
    pb = normalize_playbook(playbook)
    ordered = [str(task_id) for task_id in task_ids]
    if len(ordered) != len(set(ordered)):
        return MultiExtractCheckResult(
            task_ids=ordered,
            ok=False,
            root_checks=[],
            sequence_conflicts=[],
            reasons=["Duplicate task ids in sequence"],
        )

    root_checks = [check_potential_root(pb, task_id) for task_id in ordered]
    reasons: List[str] = []
    for check in root_checks:
        if not check.ok:
            reasons.extend(check.reasons)

    sequence_conflicts: List[JsonDict] = []
    for left_index, left_id in enumerate(ordered):
        left_successors = set(total_successors(pb, left_id))
        for right_index in range(left_index + 1, len(ordered)):
            right_id = ordered[right_index]
            right_successors = set(total_successors(pb, right_id))
            if right_id in left_successors:
                sequence_conflicts.append(
                    {
                        "earlier_task_id": left_id,
                        "later_task_id": right_id,
                        "earlier_index": left_index,
                        "later_index": right_index,
                        "direction": f"{left_id} -> {right_id}",
                    }
                )
                reasons.append(f"Task {right_id!r} is a successor of task {left_id!r}")
            if left_id in right_successors:
                sequence_conflicts.append(
                    {
                        "earlier_task_id": right_id,
                        "later_task_id": left_id,
                        "earlier_index": right_index,
                        "later_index": left_index,
                        "direction": f"{right_id} -> {left_id}",
                    }
                )
                reasons.append(f"Task {left_id!r} is a successor of task {right_id!r}")

    ok = not reasons
    return MultiExtractCheckResult(
        task_ids=ordered,
        ok=ok,
        root_checks=root_checks,
        sequence_conflicts=sequence_conflicts,
        reasons=reasons,
    )


def tasks_reaching_target(playbook: Mapping[str, object], target_id: str) -> Set[str]:
    """Task ids from which target_id is reachable, including the target itself."""
    tasks = playbook_tasks(playbook)
    target = str(target_id)
    incoming: dict[str, List[str]] = defaultdict(list)
    for source_id, node in tasks.items():
        for _, successor in iter_successors(node):
            incoming[successor].append(source_id)
    seen: Set[str] = set()
    queue: List[str] = [target]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for source_id in incoming.get(current, []):
            if source_id not in seen:
                queue.append(source_id)
    return seen


def reachable_without_end(playbook: Mapping[str, object], start_id: str, end_id: str) -> Set[str]:
    """Tasks reachable from start without visiting end (end itself is excluded)."""
    pb = normalize_playbook(playbook)
    start = str(start_id)
    end = str(end_id)
    tasks = playbook_tasks(pb)
    if start not in tasks:
        return set()
    seen: Set[str] = set()
    queue: List[str] = [start]
    while queue:
        current = queue.pop(0)
        if current == end or current in seen:
            continue
        seen.add(current)
        node = tasks.get(current)
        if not node:
            continue
        for _, target in iter_successors(node):
            if target != end and target not in seen:
                queue.append(target)
    return seen


def cluster_task_ids(playbook: Mapping[str, object], start_id: str, end_id: str) -> List[str]:
    """Tasks from start through side branches, stopping before end's strict descendants.

    Includes start/end and every task reachable from start except proper descendants of
    end (successors-only region after end). Returned in forward BFS order from start.
    """
    pb = normalize_playbook(playbook)
    start = str(start_id)
    end = str(end_id)
    tasks = playbook_tasks(pb)
    desc_start = set(descendant_ids(pb, start))
    desc_end = set(descendant_ids(pb, end))
    allowed = (desc_start - desc_end) | {end}
    ordered: List[str] = []
    seen: Set[str] = set()
    queue: List[str] = [start]
    while queue:
        current = queue.pop(0)
        if current not in allowed or current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        node = tasks.get(current)
        if not node:
            continue
        for _, target in iter_successors(node):
            if target in allowed and target not in seen:
                queue.append(target)
    return ordered


@dataclass
class ClusterExtractCheckResult:
    start_task_id: str
    end_task_id: str
    ok: bool
    cluster_task_ids: List[str]
    orphan_feeder_ids: List[str]
    bypass_task_ids: List[str]
    outside_outgoing: List[IncomingEdge]
    outside_incoming: List[IncomingEdge]
    incoming_to_start: List[IncomingEdge]
    end_outgoing: List[IncomingEdge]
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "start_task_id": self.start_task_id,
            "end_task_id": self.end_task_id,
            "ok": self.ok,
            "cluster_task_ids": list(self.cluster_task_ids),
            "orphan_feeder_ids": list(self.orphan_feeder_ids),
            "bypass_task_ids": list(self.bypass_task_ids),
            "outside_outgoing": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.outside_outgoing
            ],
            "outside_incoming": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.outside_incoming
            ],
            "incoming_to_start": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.incoming_to_start
            ],
            "end_outgoing": [
                {"source_id": e.source_id, "label": e.label, "target_id": e.target_id}
                for e in self.end_outgoing
            ],
            "reasons": list(self.reasons),
        }


def check_cluster_extract(
    playbook: Mapping[str, object],
    start_id: str,
    end_id: str,
) -> ClusterExtractCheckResult:
    """Validate a start/end task cluster for refactor into a sub-playbook."""
    pb = normalize_playbook(playbook)
    start = str(start_id)
    end = str(end_id)
    tasks = playbook_tasks(pb)
    reasons: List[str] = []

    if start not in tasks:
        reasons.append(f"Start task {start!r} does not exist in playbook")
    if end not in tasks:
        reasons.append(f"End task {end!r} does not exist in playbook")
    if reasons:
        return ClusterExtractCheckResult(
            start_task_id=start,
            end_task_id=end,
            ok=False,
            cluster_task_ids=[],
            orphan_feeder_ids=[],
            bypass_task_ids=[],
            outside_outgoing=[],
            outside_incoming=[],
            incoming_to_start=[],
            end_outgoing=[],
            reasons=reasons,
        )

    if start != end and end not in set(total_successors(pb, start)):
        reasons.append(f"End task {end!r} is not reachable from start task {start!r}")

    end_node = tasks[end]
    end_type = task_type(end_node)
    if end_type == "condition":
        reasons.append(
            f"End task {end!r} ({task_name(end_node) or end_type}) is a conditional task; "
            "cluster end must not be conditional because sub-playbook call nodes cannot "
            "express conditional successors the same way"
        )

    reaching_end = tasks_reaching_target(pb, end)
    core_cluster = cluster_task_ids(pb, start, end)
    cluster_set = set(core_cluster)
    bypass = sorted(
        reachable_without_end(pb, start, end) - cluster_set,
        key=lambda item: int(item) if str(item).isdigit() else item,
    )
    for tid in bypass:
        node = tasks.get(tid)
        reasons.append(
            f"Task {tid!r} ({task_name(node) or task_type(node) if node else tid}) is reachable from start "
            f"without passing through end task {end!r}"
        )

    outside_incoming = incoming_edges(pb, cluster_set - {start}, exclude_sources=cluster_set)
    orphan_feeders = orphan_feeders_for_leaks(pb, cluster_set, outside_incoming)
    ordered_cluster = extended_extract_task_ids(pb, core_cluster, orphan_feeders)
    outside_outgoing: List[IncomingEdge] = []
    end_outgoing: List[IncomingEdge] = []
    for tid in core_cluster:
        node = tasks.get(tid)
        if not node:
            continue
        for label, target in iter_successors(node):
            if target in cluster_set:
                continue
            edge = IncomingEdge(source_id=tid, label=label, target_id=target)
            if tid == end:
                end_outgoing.append(edge)
            else:
                outside_outgoing.append(edge)
                reasons.append(
                    f"Cluster task {tid!r} ({task_name(node) or task_type(node)}) has outside successor "
                    f"{target!r} on branch {label!r}"
                )

    allowed_leak_sources = orphan_feeders
    for edge in outside_incoming:
        if edge.source_id in allowed_leak_sources:
            continue
        reasons.append(
            f"Outside task {edge.source_id!r} --{edge.label}--> cluster task {edge.target_id!r}"
        )

    incoming_to_start = incoming_edges(pb, [start], exclude_sources=cluster_set)

    return ClusterExtractCheckResult(
        start_task_id=start,
        end_task_id=end,
        ok=not reasons,
        cluster_task_ids=ordered_cluster,
        orphan_feeder_ids=ordered_orphan_feeders(pb, cluster_set, orphan_feeders),
        bypass_task_ids=bypass,
        outside_outgoing=outside_outgoing,
        outside_incoming=outside_incoming,
        incoming_to_start=incoming_to_start,
        end_outgoing=end_outgoing,
        reasons=reasons,
    )


@dataclass
class CombinedExtractCheckResult:
    task_ids: List[str]
    clusters: List[ClusterExtractCheckResult]
    ok: bool
    root_checks: List[PotentialRootResult]
    sequence_conflicts: List[JsonDict]
    overlap_conflicts: List[JsonDict]
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "task_ids": list(self.task_ids),
            "clusters": [item.to_dict() for item in self.clusters],
            "ok": self.ok,
            "root_checks": [item.to_dict() for item in self.root_checks],
            "sequence_conflicts": list(self.sequence_conflicts),
            "overlap_conflicts": list(self.overlap_conflicts),
            "reasons": list(self.reasons),
        }


def check_combined_extract(
    playbook: Mapping[str, object],
    task_ids: Sequence[str],
    clusters: Sequence[Tuple[str, str]],
) -> CombinedExtractCheckResult:
    """Validate potential-root tasks and start/end clusters for one parent rewrite."""
    multi = check_multi_extract(playbook, task_ids)
    cluster_checks = [check_cluster_extract(playbook, start, end) for start, end in clusters]
    reasons = list(multi.reasons)
    for check in cluster_checks:
        if not check.ok:
            reasons.extend(check.reasons)

    overlap_conflicts: List[JsonDict] = []
    occupied: dict[str, str] = {}
    for check in cluster_checks:
        for tid in check.cluster_task_ids:
            if tid in occupied:
                overlap_conflicts.append(
                    {
                        "task_id": tid,
                        "first": occupied[tid],
                        "second": f"cluster:{check.start_task_id}-{check.end_task_id}",
                    }
                )
                reasons.append(f"Task {tid!r} belongs to multiple extractions")
            else:
                occupied[tid] = f"cluster:{check.start_task_id}-{check.end_task_id}"

    for task_id, root_check in zip(multi.task_ids, multi.root_checks):
        for tid in root_check.descendant_ids:
            if tid in occupied:
                overlap_conflicts.append(
                    {
                        "task_id": tid,
                        "first": occupied[tid],
                        "second": f"root:{task_id}",
                    }
                )
                reasons.append(f"Task {tid!r} belongs to root extract {task_id!r} and {occupied[tid]}")
            else:
                occupied[tid] = f"root:{task_id}"

    return CombinedExtractCheckResult(
        task_ids=list(multi.task_ids),
        clusters=cluster_checks,
        ok=not reasons,
        root_checks=multi.root_checks,
        sequence_conflicts=multi.sequence_conflicts,
        overlap_conflicts=overlap_conflicts,
        reasons=reasons,
    )
