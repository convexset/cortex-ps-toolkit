"""Load playbooks for refactor from toolkit cache only (no tenant bulk fetch)."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Optional

from ..credentials import CredentialProfile, get_profile
from .body_lookup import lookup_playbook_body
from .cache import load_playbooks_index
from .refactor_bridge import _ensure_imported

REFACTOR_CACHE_MISS_HINT = (
    "Refresh Playbook Tools (playbooks index + bodies), run analysis, then retry. "
    "Refactor validation and preview do not download playbooks from the tenant."
)


class RefactorCacheMiss(KeyError):
    """Raised when a playbook body is not available in the toolkit cache."""


def _raise_cache_miss(playbook_ref: str, profile: CredentialProfile, *, reason: str) -> None:
    raise RefactorCacheMiss(
        f"Playbook {playbook_ref!r} not in toolkit cache for profile {profile.slug!r} "
        f"(reason={reason}). {REFACTOR_CACHE_MISS_HINT}"
    )


def load_toolkit_playbook_body(
    profile_slug: str,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
) -> dict[str, Any]:
    """Return full playbook JSON from ``data/cache/.../playbooks/bodies`` (analysis stale policy)."""
    profile = get_profile(profile_slug)
    lookup = lookup_playbook_body(
        profile,
        playbook_id=playbook_id,
        playbook_name=playbook_name,
        stale_policy="analysis",
        restamp_on_analysis_mismatch=True,
    )
    ref = playbook_id or playbook_name or lookup.canonical_id or ""
    if lookup.status == "hit" and lookup.playbook is not None:
        return lookup.playbook
    _raise_cache_miss(str(ref), profile, reason=lookup.status)


def resolve_toolkit_playbook_ref(
    profile_slug: str,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
) -> str:
    if playbook_id:
        return playbook_id
    if playbook_name:
        return playbook_name
    raise ValueError("playbook_id or playbook_name is required")


def list_toolkit_playbook_summaries_by_prefix(profile_slug: str, prefix: str) -> list[dict[str, Any]]:
    profile = get_profile(profile_slug)
    rows: list[dict[str, Any]] = []
    for item in load_playbooks_index(profile).get("playbooks") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name.startswith(prefix):
            rows.append(dict(item))
    rows.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("id") or "")))
    return rows


def load_task_update_targets_from_toolkit_cache(
    profile_slug: str,
    *,
    playbook: Optional[str] = None,
    name_prefix: Optional[str] = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    if force:
        raise ValueError(
            f"force=True is not supported for refactor task-update preview; {REFACTOR_CACHE_MISS_HINT}"
        )
    if name_prefix:
        summaries = list_toolkit_playbook_summaries_by_prefix(profile_slug, name_prefix)
        targets: list[dict[str, Any]] = []
        missing: list[str] = []
        for row in summaries:
            pid = str(row.get("id") or "")
            try:
                targets.append(
                    load_toolkit_playbook_body(profile_slug, playbook_id=pid, playbook_name=str(row.get("name") or ""))
                )
            except RefactorCacheMiss:
                missing.append(pid or str(row.get("name") or ""))
        if missing:
            profile = get_profile(profile_slug)
            _raise_cache_miss(
                f"name_prefix={name_prefix!r} ({len(missing)} missing bodies)",
                profile,
                reason="missing_file",
            )
        return targets
    if not playbook:
        raise ValueError("playbook or name_prefix is required")
    return [load_toolkit_playbook_body(profile_slug, playbook_id=playbook, playbook_name=playbook)]


def _stub_playbook_index_entry(*, playbook_id: str, name: str) -> dict[str, Any]:
    """Minimal playbook document for job-cache index (id lookup during overwrite upload)."""
    return {
        "id": playbook_id,
        "name": name,
        "startTaskId": "0",
        "tasks": {"0": {"id": "0", "type": "start", "task": {"id": "0"}}},
    }


def seed_existing_overwrite_targets(
    cache: Any,
    existing_targets: Sequence[Mapping[str, Any]] | Sequence[dict[str, Any]],
) -> int:
    """Index planned overwrite targets from toolkit preflight (no tenant download)."""
    seeded = 0
    for row in existing_targets:
        playbook_id = str(row.get("playbook_id") or "").strip()
        name = str(row.get("name") or "").strip()
        if not playbook_id or not name:
            continue
        cache._upsert(_stub_playbook_index_entry(playbook_id=playbook_id, name=name))
        seeded += 1
    return seeded


def bootstrap_playbook_utils_cache_from_toolkit(
    cache: Any,
    profile_slug: str,
    playbook_ref: str,
    *,
    existing_targets: Sequence[Mapping[str, Any]] | Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Seed an isolated playbook-utils job cache so ``resolve`` skips tenant bulk refresh."""
    _ensure_imported()
    from playbook_utils.cache import CacheMeta

    playbook = load_toolkit_playbook_body(
        profile_slug,
        playbook_id=playbook_ref,
        playbook_name=playbook_ref,
    )
    cache._upsert(playbook)
    overwrite_seeded = seed_existing_overwrite_targets(cache, existing_targets or [])
    index = cache._load_index()
    meta = CacheMeta(
        url=cache.credentials.url,
        platform=cache.credentials.platform.value,
        fetched_at=time.time(),
        ttl_seconds=cache.ttl_seconds,
        playbook_count=len(index.get("by_id") or {}),
        complete=True,
    )
    cache.meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
    return {
        "seeded_playbook_id": playbook.get("id"),
        "seeded_playbook_name": playbook.get("name"),
        "indexed_playbooks": len(index.get("by_id") or {}),
        "seeded_overwrite_targets": overwrite_seeded,
    }
