"""Rebind sub-playbook task references to target tenant cache (from bay/playbook-utils)."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

from .entity_resolution import _mutable_inner
from .yaml_helpers import set_canonical, task_field


def resolve_playbook_task_bindings(
    playbook: MutableMapping[str, Any],
    *,
    name_to_id: Mapping[str, str],
    id_to_name: Optional[Mapping[str, str]] = None,
    playbook_id_remap: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Ensure playbook-call tasks use tenant playbookId/playbookName from cache."""
    unresolved: list[dict[str, Any]] = []
    id_to_name = id_to_name or {}

    for task_id, node in (playbook.get("tasks") or {}).items():
        if node.get("type") != "playbook":
            continue
        inner = _mutable_inner(node)

        playbook_id = task_field(inner, "playbookId")
        playbook_name = task_field(inner, "playbookName")
        playbook_id_str = str(playbook_id) if playbook_id else ""
        playbook_name_str = str(playbook_name) if playbook_name else ""

        if playbook_id_remap and playbook_id_str in playbook_id_remap:
            playbook_id_str = str(playbook_id_remap[playbook_id_str])
            set_canonical(inner, "playbookId", playbook_id_str)

        if playbook_id_str and playbook_id_str in name_to_id:
            resolved = name_to_id[playbook_id_str]
            set_canonical(inner, "playbookId", resolved)
            if resolved in id_to_name:
                set_canonical(inner, "playbookName", id_to_name[resolved])
            playbook_id_str = resolved
            continue

        if not playbook_id_str and playbook_name_str:
            resolved = name_to_id.get(playbook_name_str)
            if resolved:
                set_canonical(inner, "playbookId", resolved)
                playbook_id_str = resolved
            else:
                unresolved.append({
                    "task_id": task_id,
                    "playbook_name": playbook_name_str,
                    "error": "playbook name not found in cache index",
                })
                continue

        if playbook_id_str and playbook_id_str in id_to_name:
            set_canonical(inner, "playbookName", id_to_name[playbook_id_str])
            continue

        if playbook_id_str and playbook_name_str:
            resolved = name_to_id.get(playbook_name_str)
            if resolved:
                set_canonical(inner, "playbookId", resolved)
                if resolved in id_to_name:
                    set_canonical(inner, "playbookName", id_to_name[resolved])
            else:
                unresolved.append({
                    "task_id": task_id,
                    "playbook_id": playbook_id_str,
                    "playbook_name": playbook_name_str,
                    "error": "playbook id not in cache and playbookName lookup failed",
                })
            continue

        if playbook_id_str:
            unresolved.append({
                "task_id": task_id,
                "playbook_id": playbook_id_str,
                "error": "playbook id not in cache and no playbookName to re-resolve",
            })
            continue

        unresolved.append({"task_id": task_id, "error": "playbook call missing playbookId and playbookName"})

    return unresolved
