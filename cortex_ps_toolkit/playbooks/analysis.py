"""Analyze a playbook and reachable sub-playbooks from tenant cache."""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from ..cache.ensure import ensure_analysis_caches
from ..cache.pack_meta import get_cached_item_meta, save_item_meta
from ..content.item_metadata import item_metadata_row, script_metadata_row
from ..credentials import CredentialProfile, get_profile
from ..scripts import api as scripts_api
from ..scripts.cache import find_script_in_index, script_index_maps
from .entity_resolution import (
    integration_command_from_task,
    resolve_automation_script,
    sub_playbook_display_name,
)
from .flow_graph import build_flow_graphs_for_tree
from .graph import compute_completion_path_metrics, compute_playbook_task_listings, compute_task_summaries
from .resolver import CachePlaybookResolver
from .yaml_helpers import (
    iter_sub_playbook_refs,
    playbook_identity,
    script_label,
    sub_playbook_reference,
)


def _group_consecutive_sub_playbooks(
    playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> list[tuple[str, int, Optional[str], bool]]:
    ordered: list[tuple[Any, str, Optional[str], Optional[str]]] = []
    for task_id, node in (playbook.get("tasks") or {}).items():
        if node.get("type") != "playbook":
            continue
        inner = node.get("task") or {}
        pid, pname = sub_playbook_reference(inner)
        sort_key = int(task_id) if str(task_id).isdigit() else task_id
        ordered.append((sort_key, str(task_id), pid, pname))
    ordered.sort(key=lambda row: row[0])

    grouped: list[tuple[str, int, Optional[str], bool]] = []
    for _, _task_id, pid, pname in ordered:
        display_name, target, missing = sub_playbook_display_name(resolver, pid, pname)
        if grouped and grouped[-1][0] == display_name and grouped[-1][2] == target:
            prev_name, count, prev_target, prev_missing = grouped[-1]
            grouped[-1] = (prev_name, count + 1, prev_target, prev_missing)
        else:
            grouped.append((display_name, 1, target, missing))
    return grouped


def build_structure_tree_lines(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> list[str]:
    lines: list[str] = []
    _, root_name = playbook_identity(root_playbook)
    lines.append(root_name)

    def append_children(playbook: dict[str, Any], depth: int, stack: tuple[str, ...]) -> None:
        for display_name, count, target, missing in _group_consecutive_sub_playbooks(playbook, resolver):
            suffix = f" ({count}x)" if count > 1 else ""
            missing_suffix = " [MISSING]" if missing else ""
            prefix = ("    " * depth) + "+- "
            lines.append(f"{prefix}{display_name}{suffix}{missing_suffix}")
            if not target or missing:
                continue
            sub_playbook = resolver.load(target)
            sub_key = str(sub_playbook.get("id") or display_name)
            if sub_key in stack:
                lines.append(("    " * (depth + 1)) + "+- (circular reference skipped)")
                continue
            append_children(sub_playbook, depth + 1, stack + (sub_key,))

    root_key = str(root_playbook.get("id") or root_name)
    append_children(root_playbook, depth=0, stack=(root_key,))
    return lines


def build_structure_graph(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> dict[str, Any]:
    """Build a node/edge graph of sub-playbook nesting for UI rendering."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_counter = 0

    def add_node(
        *,
        playbook_id: Optional[str],
        name: str,
        missing: bool = False,
        circular: bool = False,
    ) -> str:
        nonlocal node_counter
        node_id = f"n{node_counter}"
        node_counter += 1
        nodes.append({
            "id": node_id,
            "playbook_id": playbook_id,
            "name": name,
            "missing": missing,
            "circular": circular,
        })
        return node_id

    root_id, root_name = playbook_identity(root_playbook)
    root_node = add_node(playbook_id=root_id or None, name=root_name)

    def append_children(parent_node_id: str, playbook: dict[str, Any], stack: tuple[str, ...]) -> None:
        for display_name, count, target, missing in _group_consecutive_sub_playbooks(playbook, resolver):
            if missing or not target:
                child_id = add_node(playbook_id=None, name=display_name, missing=True)
                edges.append({
                    "from": parent_node_id,
                    "to": child_id,
                    "count": count,
                    "missing": True,
                    "circular": False,
                })
                continue

            sub_playbook = resolver.load(target)
            sub_key = str(sub_playbook.get("id") or display_name)
            sub_id, _sub_name = playbook_identity(sub_playbook)
            if sub_key in stack:
                child_id = add_node(
                    playbook_id=sub_id or None,
                    name=display_name,
                    circular=True,
                )
                edges.append({
                    "from": parent_node_id,
                    "to": child_id,
                    "count": count,
                    "missing": False,
                    "circular": True,
                })
                continue

            child_id = add_node(playbook_id=sub_id or None, name=display_name)
            edges.append({
                "from": parent_node_id,
                "to": child_id,
                "count": count,
                "missing": False,
                "circular": False,
            })
            append_children(child_id, sub_playbook, stack + (sub_key,))

    root_key = str(root_playbook.get("id") or root_name)
    append_children(root_node, root_playbook, (root_key,))
    return {"nodes": nodes, "edges": edges}


def _count_playbook_occurrences(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> Counter[str]:
    occurrences: Counter[str] = Counter()
    _, root_name = playbook_identity(root_playbook)
    occurrences[root_name] = 1

    def walk(playbook: dict[str, Any], stack: tuple[str, ...]) -> None:
        for _task_id, pid, pname, _label in iter_sub_playbook_refs(playbook):
            target = resolver.resolve(pid, pname)
            if not target:
                continue
            sub_playbook = resolver.load(target)
            _, sub_name = playbook_identity(sub_playbook)
            occurrences[sub_name] += 1
            sub_key = str(sub_playbook.get("id") or sub_name)
            if sub_key in stack:
                continue
            walk(sub_playbook, stack + (sub_key,))

    root_key = str(root_playbook.get("id") or root_name)
    walk(root_playbook, (root_key,))
    return occurrences


def _walk_playbooks_in_tree(
    root_playbook: dict[str, Any],
    resolver: CachePlaybookResolver,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    playbooks: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    seen_missing: set[str] = set()

    root_id, root_name = playbook_identity(root_playbook)
    playbooks[root_id or root_name] = {
        "id": root_id,
        "name": root_name,
        "role": "root",
    }

    def walk(playbook: dict[str, Any], stack: tuple[str, ...], containing: str) -> None:
        for task_id, pid, pname, label in iter_sub_playbook_refs(playbook):
            lookup = pid or pname or ""
            target = resolver.resolve(pid, pname)
            if target:
                sub = resolver.load(target)
                sub_id, sub_name = playbook_identity(sub)
                key = sub_id or sub_name
                if key not in playbooks:
                    playbooks[key] = {
                        "id": sub_id,
                        "name": sub_name,
                        "role": "sub_playbook",
                    }
                sub_key = str(sub.get("id") or sub_name)
                if sub_key not in stack:
                    walk(sub, stack + (sub_key,), sub_name)
            elif lookup and lookup not in seen_missing:
                seen_missing.add(lookup)
                missing.append({
                    "playbook_id": pid,
                    "playbook_name": pname,
                    "lookup_key": lookup,
                    "referenced_from": containing,
                    "example_task_id": task_id,
                    "example_task_label": label,
                })

    root_key = str(root_playbook.get("id") or root_name)
    walk(root_playbook, (root_key,), root_name)
    return list(playbooks.values()), missing


def _task_breakdown(
    playbook: dict[str, Any],
    *,
    script_by_id: dict[str, dict[str, Any]] | None = None,
    script_by_name: dict[str, dict[str, Any]] | None = None,
) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for node in (playbook.get("tasks") or {}).values():
        task_type = str(node.get("type") or "unknown")
        counts[(task_type, script_label(node, script_by_id=script_by_id, script_by_name=script_by_name))] += 1
    return counts


def _resolve_script_metadata(
    profile: CredentialProfile,
    *,
    script_id: Optional[str],
    name: str,
    cache_entry: Optional[dict[str, Any]],
) -> dict[str, Any]:
    lookup_id = str(script_id or (cache_entry or {}).get("id") or name or "")
    cached_meta = get_cached_item_meta(profile, kind="scripts", item_id=lookup_id) if lookup_id else None
    if cached_meta:
        return {
            "system": bool(cached_meta.get("system")),
            "origin": cached_meta.get("origin") or "custom",
            "pack_id": cached_meta.get("pack_id"),
            "pack_name": cached_meta.get("pack_name"),
            "copyable": bool(cached_meta.get("copyable")),
        }

    document: Optional[dict[str, Any]] = None
    if cache_entry and cache_entry.get("system") is True:
        meta = script_metadata_row(cache_entry=cache_entry)
    else:
        if lookup_id:
            try:
                document = scripts_api.get_script(profile, lookup_id)
            except Exception:
                document = None
        meta = script_metadata_row(cache_entry=cache_entry, document=document)
    if lookup_id:
        save_item_meta(
            profile,
            kind="scripts",
            item_id=lookup_id,
            meta=meta,
        )
    return meta


def _resolve_playbook_metadata(
    profile: CredentialProfile,
    resolver: CachePlaybookResolver,
    *,
    playbook_id: str,
    cache_entry: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    cached_meta = get_cached_item_meta(profile, kind="playbooks", item_id=playbook_id)
    if cached_meta:
        return {
            "system": bool(cached_meta.get("system")),
            "origin": cached_meta.get("origin") or "custom",
            "pack_id": cached_meta.get("pack_id"),
            "pack_name": cached_meta.get("pack_name"),
            "copyable": bool(cached_meta.get("copyable")),
        }

    document: Optional[dict[str, Any]] = None
    try:
        document = resolver.load(playbook_id)
    except Exception:
        document = None
    meta = item_metadata_row(cache_entry=cache_entry or resolver.meta(playbook_id), document=document)
    save_item_meta(profile, kind="playbooks", item_id=playbook_id, meta=meta)
    return meta


def _enrich_playbooks_in_tree(
    profile: CredentialProfile,
    playbooks_in_tree: list[dict[str, Any]],
    resolver: CachePlaybookResolver,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for entry in playbooks_in_tree:
        pb_id = str(entry.get("id") or "")
        row = dict(entry)
        if pb_id:
            row.update(_resolve_playbook_metadata(profile, resolver, playbook_id=pb_id))
        enriched.append(row)
    return enriched


def _collect_scripts_and_commands(
    playbooks: list[dict[str, Any]],
    resolver: CachePlaybookResolver,
    profile_slug: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    script_counts: Counter[str] = Counter()
    script_ids_by_name: dict[str, str] = {}
    script_playbooks: dict[str, set[str]] = {}
    integration_counts: Counter[str] = Counter()
    integration_meta: dict[str, dict[str, Any]] = {}
    profile = get_profile(profile_slug)
    script_by_id, script_by_name = script_index_maps(profile)

    for entry in playbooks:
        pb_id = str(entry.get("id") or "")
        if not pb_id:
            continue
        playbook = resolver.load(pb_id)
        _, pb_name = playbook_identity(playbook)
        for node in (playbook.get("tasks") or {}).values():
            integration = integration_command_from_task(node, script_by_id=script_by_id)
            if integration:
                key = integration["command"]
                integration_counts[key] += 1
                existing = integration_meta.get(key)
                if existing is None:
                    integration_meta[key] = dict(integration)
                elif integration.get("raw") and not existing.get("raw"):
                    existing["raw"] = integration["raw"]

            automation = resolve_automation_script(
                node,
                script_by_id=script_by_id,
                script_by_name=script_by_name,
            )
            if not automation:
                continue

            script_counts[automation.canonical_name] += 1
            script_playbooks.setdefault(automation.canonical_name, set()).add(pb_name)
            if automation.script_id:
                script_ids_by_name[automation.canonical_name] = automation.script_id

    scripts_used: list[dict[str, Any]] = []
    unresolved_scripts: list[dict[str, Any]] = []
    for name, count in script_counts.most_common():
        cached = find_script_in_index(profile, name=name, script_id=script_ids_by_name.get(name))
        script_id = str((cached or {}).get("id") or script_ids_by_name.get(name) or "") or None
        meta = _resolve_script_metadata(
            profile,
            script_id=script_id,
            name=name,
            cache_entry=cached,
        )
        row = {
            "name": name,
            "count": count,
            "playbooks": sorted(script_playbooks.get(name, set())),
            "script_id": script_id,
            "resolved": cached is not None,
            **meta,
        }
        scripts_used.append(row)
        if not cached:
            unresolved_scripts.append(row)

    integration_commands_used = [
        {
            "command": command,
            "count": count,
            "raw": integration_meta.get(command, {}).get("raw"),
            "resolved": integration_meta.get(command, {}).get("resolved", True),
            "copy_required": False,
        }
        for command, count in integration_counts.most_common()
    ]

    return scripts_used, integration_commands_used, unresolved_scripts


def analyze_playbook(
    profile: str,
    playbook_id: str,
    *,
    resolver: Optional[CachePlaybookResolver] = None,
) -> dict[str, Any]:
    """Analyze playbook structure, tasks, scripts, and commands from tenant cache."""
    resolved = get_profile(profile)
    cache_info = ensure_analysis_caches(resolved)
    script_by_id, script_by_name = script_index_maps(resolved)
    resolver = resolver or CachePlaybookResolver(resolved)
    root = resolver.load(playbook_id)
    root_id, root_name = playbook_identity(root)

    playbooks_in_tree, missing_sub_playbooks = _walk_playbooks_in_tree(root, resolver)
    playbooks_in_tree = _enrich_playbooks_in_tree(resolved, playbooks_in_tree, resolver)
    occurrences = _count_playbook_occurrences(root, resolver)
    structure_tree = build_structure_tree_lines(root, resolver)
    structure_graph = build_structure_graph(root, resolver)
    flow_graphs = build_flow_graphs_for_tree(
        playbooks_in_tree,
        root,
        resolver,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )

    task_summary_reachable, task_summary_unreachable, task_summary, task_reachability_totals = compute_task_summaries(
        playbooks_in_tree,
        root,
        resolver,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )
    playbook_task_listings = compute_playbook_task_listings(
        playbooks_in_tree,
        root,
        resolver,
        script_by_id=script_by_id,
        script_by_name=script_by_name,
    )
    completion_paths = compute_completion_path_metrics(root, resolver)

    scripts_used, integration_commands_used, unresolved_scripts = _collect_scripts_and_commands(
        playbooks_in_tree,
        resolver,
        profile,
    )

    playbook_ids = [str(entry.get("id") or "") for entry in playbooks_in_tree if entry.get("id")]
    copyable_script_ids = [
        row["script_id"]
        for row in scripts_used
        if row.get("script_id") and row.get("copyable")
    ]
    excluded_scripts = [
        {
            "script_id": row.get("script_id"),
            "name": row.get("name"),
            "origin": row.get("origin"),
            "system": row.get("system"),
            "pack_id": row.get("pack_id"),
            "pack_name": row.get("pack_name"),
            "reason": "system_script" if row.get("system") else "content_pack_script",
        }
        for row in scripts_used
        if row.get("script_id") and not row.get("copyable")
    ]
    script_ids = copyable_script_ids

    notes = _build_notes(
        missing_sub_playbooks=missing_sub_playbooks,
        unresolved_scripts=unresolved_scripts,
        completion_paths=completion_paths,
        task_reachability_totals=task_reachability_totals,
        structure_tree=structure_tree,
        playbooks_in_tree=playbooks_in_tree,
    )

    refactor_task_catalog: list[dict[str, Any]] = []
    try:
        from .refactor_graph_validation import build_refactor_task_catalog

        refactor_task_catalog = build_refactor_task_catalog(root)
    except Exception:
        refactor_task_catalog = []

    return {
        "profile": profile,
        "cache": cache_info,
        "root_playbook": {
            "id": root_id,
            "name": root_name,
        },
        "structure_tree": structure_tree,
        "structure_graph": structure_graph,
        "flow_graphs": flow_graphs,
        "refactor_task_catalog": refactor_task_catalog,
        "playbook_occurrences": dict(occurrences.most_common()),
        "playbooks_in_tree": playbooks_in_tree,
        "missing_sub_playbooks": missing_sub_playbooks,
        "task_summary": task_summary,
        "task_summary_reachable": task_summary_reachable,
        "task_summary_unreachable": task_summary_unreachable,
        "task_reachability_totals": task_reachability_totals,
        "completion_paths": completion_paths,
        "playbook_task_listings": playbook_task_listings,
        "scripts_used": scripts_used,
        "integration_commands_used": integration_commands_used,
        "commands_used": integration_commands_used,
        "unresolved_scripts": unresolved_scripts,
        "copy_scope": {
            "playbook_ids": playbook_ids,
            "script_ids": script_ids,
            "playbook_count": len(playbook_ids),
            "script_count": len(script_ids),
            "excluded_script_count": len(excluded_scripts),
            "excluded_scripts": excluded_scripts,
            "integration_command_count": len(integration_commands_used),
            "missing_sub_playbook_count": len(missing_sub_playbooks),
            "unresolved_script_count": len(unresolved_scripts),
        },
        "notes": notes,
        "warnings": _notes_as_warnings(notes),
    }


def _build_notes(
    *,
    missing_sub_playbooks: list[dict[str, Any]],
    unresolved_scripts: list[dict[str, Any]],
    completion_paths: dict[str, Any],
    task_reachability_totals: dict[str, int],
    structure_tree: list[str],
    playbooks_in_tree: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []

    for item in missing_sub_playbooks:
        notes.append({
            "level": "warning",
            "message": f"Missing sub-playbook: {item['lookup_key']}",
            "detail": (
                f"Referenced from {item['referenced_from']} "
                f"(task {item['example_task_id']}: {item['example_task_label']})"
            ),
        })

    for item in unresolved_scripts:
        playbooks = ", ".join(item.get("playbooks") or [])
        notes.append({
            "level": "warning",
            "message": f"Script not in cache: {item['name']}",
            "detail": (
                f"Used {item['count']} time(s)"
                + (f" in {playbooks}" if playbooks else "")
                + ". Refresh scripts cache on the source tenant."
            ),
        })

    path_note = completion_paths.get("note")
    if path_note:
        notes.append({
            "level": "warning",
            "message": str(path_note),
            "detail": "Path metrics may be incomplete when sub-playbooks are missing or the graph has cycles.",
        })

    unreachable = int(task_reachability_totals.get("unreachable") or 0)
    if unreachable:
        notes.append({
            "level": "info",
            "message": f"{unreachable} task(s) are unreachable from the start node in the expanded graph.",
            "detail": "Unreachable tasks are not on any path from start through sub-playbook inlining.",
        })

    min_tasks = completion_paths.get("min_tasks_to_completion")
    max_tasks = completion_paths.get("max_tasks_to_completion")
    terminal_count = int(completion_paths.get("terminal_count") or 0)
    if min_tasks is not None and max_tasks is not None:
        if terminal_count > 1:
            notes.append({
                "level": "info",
                "message": (
                    f"Completion path: {min_tasks}–{max_tasks} sequential task(s) "
                    f"across {terminal_count} terminal branch(es)."
                ),
                "detail": "Min is the shortest path to any terminal; max is the longest path to any terminal.",
            })
        else:
            notes.append({
                "level": "info",
                "message": f"Completion path: {min_tasks} sequential task(s) to the single terminal branch.",
            })

    circular_lines = [line.strip() for line in structure_tree if "(circular reference skipped)" in line]
    if circular_lines:
        notes.append({
            "level": "warning",
            "message": "Circular sub-playbook reference detected in structure tree.",
            "detail": "; ".join(circular_lines[:3]),
        })

    sub_count = sum(1 for entry in playbooks_in_tree if entry.get("role") == "sub_playbook")
    if sub_count:
        notes.append({
            "level": "info",
            "message": f"{sub_count} resolved sub-playbook(s) included in this analysis tree.",
        })

    notes.append({
        "level": "info",
        "message": "Deep copy includes custom automation scripts and playbooks only.",
        "detail": (
            "System and content-pack scripts are reference-only. "
            "Integration commands (Brand|||command) are tenant-provided and are not copied."
        ),
    })

    if not notes:
        notes.append({
            "level": "info",
            "message": "No warnings or issues detected.",
        })

    return notes


def _notes_as_warnings(notes: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for note in notes:
        if note.get("level") not in {"warning", "error"}:
            continue
        text = str(note.get("message") or "")
        detail = note.get("detail")
        if detail:
            text = f"{text} {detail}"
        warnings.append(text)
    return warnings
