"""Resolve sub-playbook call bindings from the tenant cache before YAML upload."""

from __future__ import annotations

import copy
from typing import Iterable, List, Mapping, MutableMapping, Optional

from .cache import PlaybookCache
from .keys import JsonDict, get_field, inner_task, playbook_tasks, pop_field, set_canonical, task_name, task_type


def name_to_id_map(cache: PlaybookCache) -> dict[str, str]:
    """Build a unique playbook-name → id map from the cache index."""
    index = cache._load_index()
    mapping: dict[str, str] = {}
    for name, ids in (index.get("by_name") or {}).items():
        if len(ids) == 1:
            mapping[str(name)] = str(ids[0])
    return mapping


def id_to_name_map(cache: PlaybookCache) -> dict[str, str]:
    """Build playbook-id → name from the cache index."""
    index = cache._load_index()
    mapping: dict[str, str] = {}
    for pid, summary in (index.get("by_id") or {}).items():
        name = str((summary or {}).get("name") or "")
        if name:
            mapping[str(pid)] = name
    return mapping


def resolve_playbook_task_bindings(
    playbook: MutableMapping[str, object],
    *,
    name_to_id: Mapping[str, str],
    id_to_name: Optional[Mapping[str, str]] = None,
) -> List[JsonDict]:
    """Ensure playbook call nodes have tenant ``playbookId`` / ``playbookName`` from cache.

    Task display titles (``inner.name``) are never used as playbook names — only
    ``playbookName`` and cache lookups by ``playbookId`` are authoritative.

    Mutates ``playbook`` in place. Returns unresolved binding records (empty when
    every playbook call could be resolved).
    """
    unresolved: List[JsonDict] = []
    id_to_name = id_to_name or {}

    for tid, node in playbook_tasks(playbook).items():
        if task_type(node) != "playbook":
            continue
        inner = inner_task(node)
        if not inner:
            unresolved.append(
                {
                    "task_id": tid,
                    "task_title": task_name(node),
                    "error": "playbook task has no inner task",
                }
            )
            continue

        playbook_id = get_field(inner, "playbookId")
        playbook_name = get_field(inner, "playbookName")
        playbook_id_str = str(playbook_id) if playbook_id else ""
        playbook_name_str = str(playbook_name) if playbook_name else ""

        if not playbook_id_str and playbook_name_str:
            resolved = name_to_id.get(playbook_name_str)
            if resolved:
                set_canonical(inner, "playbookId", resolved)
                playbook_id_str = resolved
            else:
                unresolved.append(
                    {
                        "task_id": tid,
                        "task_title": task_name(node),
                        "playbook_name": playbook_name_str,
                        "error": "playbook name not found in cache index",
                    }
                )
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
                unresolved.append(
                    {
                        "task_id": tid,
                        "task_title": task_name(node),
                        "playbook_id": playbook_id_str,
                        "playbook_name": playbook_name_str,
                        "error": "playbook id not in cache and playbookName lookup failed",
                    }
                )
            continue

        if playbook_id_str:
            unresolved.append(
                {
                    "task_id": tid,
                    "task_title": task_name(node),
                    "playbook_id": playbook_id_str,
                    "error": "playbook id not in cache and no playbookName to re-resolve",
                }
            )
            continue

        unresolved.append(
            {
                "task_id": tid,
                "task_title": task_name(node),
                "error": "playbook call has no playbookId or playbookName",
            }
        )

    return unresolved


def _looks_like_playbook_uuid(value: str) -> bool:
    text = value.strip()
    return len(text) == 36 and text.count("-") >= 4


def normalize_playbook_call_ids_for_compare(
    playbook: MutableMapping[str, object],
    *,
    name_to_id: Mapping[str, str],
    id_to_name: Mapping[str, str],
    task_ids: Optional[Iterable[str]] = None,
) -> None:
    """Rewrite playbook-call ``playbookId`` values to tenant UUIDs using the cache index."""
    allowed = {str(task_id) for task_id in task_ids} if task_ids is not None else None
    for tid, node in playbook_tasks(playbook).items():
        if allowed is not None and tid not in allowed:
            continue
        if task_type(node) != "playbook":
            continue
        inner = inner_task(node)
        if not inner:
            continue
        pid = str(get_field(inner, "playbookId") or "").strip()
        pname = str(get_field(inner, "playbookName") or "").strip()

        resolved = ""
        if pid and pid in id_to_name:
            resolved = pid
        elif pid and pid in name_to_id:
            resolved = name_to_id[pid]
        elif pname and pname in name_to_id:
            resolved = name_to_id[pname]
        elif pid and _looks_like_playbook_uuid(pid):
            resolved = pid
        elif pid:
            resolved = name_to_id.get(pid, pid)

        if resolved:
            set_canonical(inner, "playbookId", resolved)
            pop_field(inner, "playbookName")


def inherit_playbook_bindings_from_source(
    downloaded: MutableMapping[str, object],
    source: Mapping[str, object],
    *,
    task_ids: Optional[Iterable[str]] = None,
) -> None:
    """Copy ``playbookId`` / ``playbookName`` from source when download JSON omits them."""
    dl_tasks = playbook_tasks(downloaded)
    src_tasks = playbook_tasks(source)
    ids = [str(tid) for tid in task_ids] if task_ids is not None else list(dl_tasks.keys())
    for tid in ids:
        dl_node = dl_tasks.get(tid)
        src_node = src_tasks.get(tid)
        if not isinstance(dl_node, dict) or not isinstance(src_node, dict):
            continue
        if task_type(dl_node) != "playbook":
            continue
        dl_inner = inner_task(dl_node)
        src_inner = inner_task(src_node)
        if not dl_inner or not src_inner:
            continue
        if get_field(dl_inner, "playbookId") or get_field(dl_inner, "playbookName"):
            continue
        src_pid = get_field(src_inner, "playbookId")
        src_pname = get_field(src_inner, "playbookName")
        if src_pid:
            set_canonical(dl_inner, "playbookId", str(src_pid))
        if src_pname:
            set_canonical(dl_inner, "playbookName", str(src_pname))


def prepare_playbook_for_yaml_export(
    playbook: Mapping[str, object],
    cache: PlaybookCache,
) -> tuple[JsonDict, JsonDict]:
    """Resolve cache bindings before YAML upload."""
    prepared = copy.deepcopy(dict(playbook))
    n2i = name_to_id_map(cache)
    i2n = id_to_name_map(cache)
    unresolved = resolve_playbook_task_bindings(
        prepared,
        name_to_id=n2i,
        id_to_name=i2n,
    )
    meta: JsonDict = {"unresolved_bindings": unresolved}
    return prepared, meta
