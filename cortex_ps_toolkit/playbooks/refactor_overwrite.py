"""Detect and gate overwrite of existing refactor target playbooks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional, Sequence

from ..credentials import get_profile
from .cache import find_playbook_in_index


def coalesce_overwrite_existing(value: object | None, *, default: bool = True) -> bool:
    """Request bodies omitting overwrite_existing use ``default`` (True for execute)."""
    if value is None:
        return default
    return bool(value)


def list_refactor_name_conflicts(
    profile_slug: str,
    *,
    subplaybook_names: Sequence[str],
    parent_copy_name: Optional[str] = None,
    source_playbook_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return tenant cache index hits for planned refactor output names."""
    profile = get_profile(profile_slug)
    source_id = str(source_playbook_id or "").strip()
    seen: set[str] = set()
    conflicts: list[dict[str, Any]] = []

    def _add(role: str, name: str) -> None:
        key = name.strip()
        if not key or key in seen:
            return
        seen.add(key)
        entry = find_playbook_in_index(profile, name=key)
        if not entry:
            return
        playbook_id = str(entry.get("id") or "")
        if source_id and playbook_id == source_id:
            return
        conflicts.append(
            {
                "role": role,
                "name": key,
                "playbook_id": playbook_id or None,
                "modified": entry.get("modified"),
            }
        )

    for name in subplaybook_names:
        _add("sub_playbook", str(name))
    if parent_copy_name:
        _add("parent_copy", str(parent_copy_name))
    return conflicts


def validate_overwrite_request(
    *,
    overwrite_existing: bool,
    overwrite_confirmed: bool,
    conflicts: Sequence[Mapping[str, Any]] | Sequence[dict[str, Any]],
) -> None:
    """Require explicit confirmation before overwriting existing playbooks."""
    conflict_list = list(conflicts)
    if not overwrite_existing:
        if overwrite_confirmed:
            raise ValueError("overwrite_confirmed cannot be set without overwrite_existing")
        return
    if conflict_list and not overwrite_confirmed:
        names = ", ".join(str(item.get("name") or "?") for item in conflict_list)
        raise ValueError(
            "Refactor would replace existing playbook(s) on the tenant: "
            f"{names}. Set overwrite_confirmed=true after user confirmation."
        )

