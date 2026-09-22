"""Plan tenant fetches needed for cache-only playbook analysis."""

from __future__ import annotations

from typing import Any

from ..cache.ensure import check_analysis_caches
from ..credentials import CredentialProfile, get_profile
from .body_lookup import (
    _body_matches_index,
    count_playbook_bodies_on_disk,
    lookup_playbook_body,
    read_cached_playbook_document,
    resolve_playbook_ref,
)
from .cache import load_playbooks_index
from .resolver import CachePlaybookResolver
from .yaml_helpers import iter_sub_playbook_refs


def plan_analysis_fetch_needs(profile: CredentialProfile | str, playbook_id: str) -> dict[str, Any]:
    """List stale indexes and playbook YAML bodies that still need a tenant GET.

    Uses the same analysis stale policy as ``analyze_playbook`` (local bodies may be
    reused when index ``modified`` changed but id/name still match).
    """
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cache_info = check_analysis_caches(resolved)
    index = load_playbooks_index(resolved)
    index_count = len(index.get("playbooks") or [])
    bodies_on_disk = count_playbook_bodies_on_disk(resolved)

    resolver = CachePlaybookResolver(resolved, allow_live_fetch=False, body_stale_policy="analysis")

    canonical_id, _meta, _display = resolve_playbook_ref(
        resolved,
        playbook_id=playbook_id,
        playbook_name=playbook_id,
    )
    root_id = (
        canonical_id
        or resolver.resolve(playbook_id, None)
        or resolver.resolve(None, playbook_id)
        or str(playbook_id)
    )
    queue: list[str] = [str(root_id)]
    visited: set[str] = set()
    bodies_needed: list[dict[str, str]] = []
    bodies_cached = 0
    partial_plan = False

    while queue:
        pb_id = queue.pop(0)
        if pb_id in visited:
            continue
        visited.add(pb_id)

        lookup = lookup_playbook_body(
            resolved,
            playbook_id=pb_id,
            stale_policy="analysis",
            restamp_on_analysis_mismatch=False,
        )
        name = lookup.name or pb_id

        if lookup.status == "hit" and lookup.playbook is not None:
            bodies_cached += 1
            body = lookup.playbook
            for _task_id, pid, pname, _label in iter_sub_playbook_refs(body):
                target = resolver.resolve(pid, pname)
                if target and target not in visited:
                    queue.append(str(target))
            continue

        if lookup.status == "modified_mismatch":
            partial_plan = True
            bodies_needed.append(
                {
                    "id": lookup.canonical_id or pb_id,
                    "name": name,
                    "reason": "modified_mismatch",
                },
            )
            body = read_cached_playbook_document(resolved, lookup.canonical_id or pb_id)
            index_meta = lookup.index_meta
            if body is not None and index_meta and _body_matches_index(body, index_meta):
                bodies_cached += 1
                for _task_id, pid, pname, _label in iter_sub_playbook_refs(body):
                    target = resolver.resolve(pid, pname)
                    if target and target not in visited:
                        queue.append(str(target))
            continue

        reason = lookup.status if lookup.status in ("missing_file", "not_in_index") else "missing_file"
        bodies_needed.append({"id": lookup.canonical_id or pb_id, "name": name, "reason": reason})
        partial_plan = True

    missing_file = [row for row in bodies_needed if row.get("reason") == "missing_file"]
    not_in_index = [row for row in bodies_needed if row.get("reason") == "not_in_index"]
    modified_mismatch = [row for row in bodies_needed if row.get("reason") == "modified_mismatch"]

    tenant_fetch_count = len(missing_file) + len(not_in_index) + len(modified_mismatch)

    return {
        "profile": resolved.slug,
        "playbook_id": str(playbook_id),
        "index_playbook_count": index_count,
        "playbook_bodies_on_disk_count": bodies_on_disk,
        "stale_scopes": list(cache_info.get("stale_scopes") or []),
        "any_stale": bool(cache_info.get("any_stale")),
        "playbook_bodies_needed": bodies_needed,
        "playbook_bodies_needed_count": tenant_fetch_count,
        "playbook_bodies_missing_file_count": len(missing_file),
        "playbook_bodies_not_in_index_count": len(not_in_index),
        "playbook_bodies_modified_mismatch_count": len(modified_mismatch),
        "playbook_bodies_cached_count": bodies_cached,
        "playbook_bodies_resync_local_count": 0,
        "partial_plan": partial_plan and bool(bodies_needed),
        "cache_layers": {
            "index": "playbook list metadata from last refresh (search API)",
            "bodies": "per-playbook task YAML on disk under playbooks/bodies/",
        },
    }
