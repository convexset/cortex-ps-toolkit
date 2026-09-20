"""Map source tenant script IDs to target tenant IDs after a component copy."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_debug, op_info
from ..scripts.cache import find_script_in_index


def build_script_id_remap(
    plan_script_items: list[dict[str, Any]],
    script_results: list[dict[str, Any]],
    target: CredentialProfile | str,
) -> dict[str, str]:
    """Build source script id → target script id using copy results and target cache."""
    resolved_target = get_profile(target) if isinstance(target, str) else target
    results_by_id = {str(row.get("script_id") or ""): row for row in script_results}
    remap: dict[str, str] = {}

    for item in plan_script_items:
        source_id = str(item.get("script_id") or "")
        if not source_id:
            continue
        result = results_by_id.get(source_id) or {}
        target_id = str(result.get("target_script_id") or item.get("target_id") or "")
        if not target_id:
            name = str(item.get("name") or "")
            entry = find_script_in_index(resolved_target, name=name) if name else None
            target_id = str(entry.get("id") or "") if entry else ""
        if target_id:
            remap[source_id] = target_id
            op_debug(
                "Script remap %s → %s (%s)",
                source_id,
                target_id,
                item.get("name") or "?",
            )

    if remap:
        op_info(
            "Built script id remap on %s: %d entr%s",
            resolved_target.slug,
            len(remap),
            "y" if len(remap) == 1 else "ies",
        )
    return remap
