"""Resolve playbook refs and load cached bodies with explicit miss reasons."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Optional

from ..credentials import CredentialProfile
from .cache import find_playbook_in_index, playbook_body_path, playbooks_bodies_dir
from .yaml_helpers import playbook_identity

StalePolicy = Literal["strict", "analysis"]
BodyLookupStatus = Literal[
    "hit",
    "missing_file",
    "modified_mismatch",
    "not_in_index",
    "invalid_payload",
    "identity_mismatch",
]


@dataclass(frozen=True)
class PlaybookBodyLookup:
    playbook: Optional[dict[str, Any]]
    canonical_id: str
    name: str
    status: BodyLookupStatus
    index_meta: Optional[dict[str, Any]]
    restamped_modified: bool = False


def count_playbook_bodies_on_disk(profile: CredentialProfile) -> int:
    bodies_dir = playbooks_bodies_dir(profile)
    if not bodies_dir.is_dir():
        return 0
    return sum(1 for path in bodies_dir.glob("*.json") if path.is_file())


def resolve_playbook_ref(
    profile: CredentialProfile,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
) -> tuple[Optional[str], Optional[dict[str, Any]], str]:
    """Map id and/or name to canonical index id (same rules as CachePlaybookResolver.resolve)."""
    pid = str(playbook_id).strip() if playbook_id else None
    pname = str(playbook_name).strip() if playbook_name else None

    meta: Optional[dict[str, Any]] = None
    if pid:
        meta = find_playbook_in_index(profile, playbook_id=pid)
    if meta is None and pname:
        meta = find_playbook_in_index(profile, name=pname)
    if meta is None and pid:
        meta = find_playbook_in_index(profile, name=pid)
    if meta is None and pname:
        meta = find_playbook_in_index(profile, playbook_id=pname)

    if meta:
        canonical_id = str(meta.get("id") or "")
        display_name = str(meta.get("name") or pname or pid or canonical_id)
        return (canonical_id or None), meta, display_name

    fallback_id = pid or pname or ""
    display_name = pname or pid or ""
    return (fallback_id or None), None, display_name


def _body_matches_index(playbook: dict[str, Any], index_meta: dict[str, Any]) -> bool:
    doc_id, doc_name = playbook_identity(playbook)
    index_id = str(index_meta.get("id") or "")
    index_name = str(index_meta.get("name") or "")
    if index_id and doc_id and index_id == doc_id:
        return True
    if index_name and doc_name and index_name == doc_name:
        return True
    return False


def _restamp_body_modified(profile: CredentialProfile, canonical_id: str, index_modified: Any) -> None:
    path = playbook_body_path(profile, canonical_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return
    from datetime import datetime, timezone

    payload["modified"] = index_modified
    payload["cached_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def lookup_playbook_body(
    profile: CredentialProfile,
    *,
    playbook_id: Optional[str] = None,
    playbook_name: Optional[str] = None,
    stale_policy: StalePolicy = "strict",
    restamp_on_analysis_mismatch: bool = True,
) -> PlaybookBodyLookup:
    """Load a cached playbook body by id/name with strict or analysis stale handling."""
    canonical_id, index_meta, display_name = resolve_playbook_ref(
        profile,
        playbook_id=playbook_id,
        playbook_name=playbook_name,
    )
    if not canonical_id:
        return PlaybookBodyLookup(
            playbook=None,
            canonical_id="",
            name=display_name,
            status="not_in_index",
            index_meta=None,
        )

    if index_meta is None:
        index_meta = find_playbook_in_index(profile, playbook_id=canonical_id)

    path = playbook_body_path(profile, canonical_id)
    if not path.exists():
        return PlaybookBodyLookup(
            playbook=None,
            canonical_id=canonical_id,
            name=display_name,
            status="missing_file",
            index_meta=index_meta,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return PlaybookBodyLookup(
            playbook=None,
            canonical_id=canonical_id,
            name=display_name,
            status="invalid_payload",
            index_meta=index_meta,
        )
    playbook = payload.get("playbook")
    if not isinstance(playbook, dict):
        return PlaybookBodyLookup(
            playbook=None,
            canonical_id=canonical_id,
            name=display_name,
            status="invalid_payload",
            index_meta=index_meta,
        )

    cached_modified = payload.get("modified")
    index_modified = (index_meta or {}).get("modified")
    if index_meta and cached_modified != index_modified:
        if stale_policy == "analysis" and _body_matches_index(playbook, index_meta):
            if restamp_on_analysis_mismatch:
                _restamp_body_modified(profile, canonical_id, index_modified)
            return PlaybookBodyLookup(
                playbook=playbook,
                canonical_id=canonical_id,
                name=display_name,
                status="hit",
                index_meta=index_meta,
                restamped_modified=restamp_on_analysis_mismatch,
            )
        return PlaybookBodyLookup(
            playbook=None,
            canonical_id=canonical_id,
            name=display_name,
            status="modified_mismatch",
            index_meta=index_meta,
        )

    return PlaybookBodyLookup(
        playbook=playbook,
        canonical_id=canonical_id,
        name=display_name,
        status="hit",
        index_meta=index_meta,
    )


def read_cached_playbook_document(profile: CredentialProfile, canonical_id: str) -> Optional[dict[str, Any]]:
    """Return playbook dict from disk without stale checks (planning / subtree walk)."""
    path = playbook_body_path(profile, canonical_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    playbook = payload.get("playbook")
    return dict(playbook) if isinstance(playbook, dict) else None


def load_playbook_body_strict(profile: CredentialProfile, playbook_id: str) -> Optional[dict[str, Any]]:
    """Backward-compatible strict load by canonical playbook id."""
    result = lookup_playbook_body(profile, playbook_id=playbook_id, stale_policy="strict")
    return result.playbook if result.status == "hit" else None
