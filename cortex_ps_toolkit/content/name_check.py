"""Lightweight target-tenant name collision checks for copy-as-new UX."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from ..credentials import CredentialProfile, get_profile
from ..design_content.service import list_cached_items as list_design_cached_items
from ..design_content.types import ASSET_KINDS, AssetKind
from ..lists.cache import find_list_in_index
from ..playbooks.cache import find_playbook_in_index
from ..scripts.cache import find_script_in_index
from .copy_modes import proposed_name

NameCheckKind = Literal["lists", "scripts", "playbooks", "design"]


def _lookup_on_target(
    target: CredentialProfile,
    kind: NameCheckKind,
    name: str,
    *,
    asset: Optional[AssetKind] = None,
) -> Optional[dict[str, Any]]:
    if kind == "lists":
        return find_list_in_index(target, name=name)
    if kind == "scripts":
        return find_script_in_index(target, name=name)
    if kind == "playbooks":
        return find_playbook_in_index(target, name=name)
    if kind == "design":
        if not asset or asset not in ASSET_KINDS:
            raise ValueError("asset required when kind is design")
        for row in list_design_cached_items(target, asset):
            if str(row.get("name") or row.get("id") or "") == name:
                return row
        return None
    raise ValueError(f"Unknown kind: {kind!r}")


def check_proposed_names(
    target_profile: CredentialProfile | str,
    kind: NameCheckKind,
    proposals: Sequence[Mapping[str, Any]],
    *,
    asset: Optional[str] = None,
) -> dict[str, Any]:
    """Return per-proposal collision status on the target tenant cache."""
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    design_asset: Optional[AssetKind] = None
    if kind == "design":
        if not asset:
            raise ValueError("asset required for design name check")
        design_asset = asset  # type: ignore[assignment]

    checks: list[dict[str, Any]] = []
    collision_count = 0
    for row in proposals:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or row.get("id") or row.get("source_name") or "")
        source_name = str(row.get("source_name") or row.get("name") or key)
        proposed = str(row.get("proposed_name") or source_name).strip()
        if not proposed:
            proposed = source_name
        existing = _lookup_on_target(target, kind, proposed, asset=design_asset)
        exists = existing is not None
        if exists:
            collision_count += 1
        checks.append(
            {
                "key": key,
                "source_name": source_name,
                "proposed_name": proposed,
                "exists": exists,
                "target_id": str(existing.get("id") or "") if existing else None,
            },
        )
    return {
        "target_profile": target.slug,
        "kind": kind,
        "asset": asset,
        "checks": checks,
        "collision_count": collision_count,
        "all_available": collision_count == 0,
    }


def proposals_from_copy_selection(
    *,
    kind: NameCheckKind,
    items: Sequence[Mapping[str, Any]],
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Build proposal rows from selected grid items (id + name)."""
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("key") or item.get("name") or "")
        source_name = str(item.get("name") or key)
        proposed = proposed_name(
            source_name,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            item_key=key,
        )
        out.append({"key": key, "source_name": source_name, "proposed_name": proposed})
    return out
