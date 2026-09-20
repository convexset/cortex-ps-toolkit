"""Ordered cross-tenant copy workflow for design-time content."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.long_op_progress import LongOperationProgress
from ..credentials import get_profile
from .copy import copy_assets_to_tenant
from .types import ORCHESTRATOR_ASSET_ORDER, AssetKind

ProgressCallback = Callable[[dict[str, Any]], None]


def execute_cross_tenant_workflow(
    source_profile: str,
    target_profile: str,
    selections: dict[str, list[str]],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
    prefer_direct_on_xsoar6: bool = True,
    include_correlation_rules: bool = False,
    correlation_rule_names: Optional[list[str]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, Any]:
    """Copy assets in dependency order: fields → layouts → types → classifiers → preprocess."""
    source = get_profile(source_profile)
    target = get_profile(target_profile)
    ordered_assets: list[AssetKind] = list(ORCHESTRATOR_ASSET_ORDER)
    asset_results: dict[str, Any] = {}
    halted = False
    halt_reason: Optional[str] = None

    pending: list[dict[str, Any]] = []
    for asset in ordered_assets:
        ids = selections.get(asset) or []
        if ids:
            pending.append({"asset": asset, "item_ids": ids, "status": "pending"})

    if include_correlation_rules and correlation_rule_names:
        pending.append({
            "asset": "correlation-rules",
            "item_ids": correlation_rule_names,
            "status": "pending",
        })

    with LongOperationProgress(on_progress, action="design_content.orchestrate") as progress:
        progress.set_in_flight(pending)
        for step in pending:
            asset = str(step["asset"])
            item_ids = [str(item) for item in step["item_ids"]]
            progress.set_current(asset=asset, item_count=len(item_ids), status="running")
            progress.set_in_flight([
                {**item, "status": "running" if item["asset"] == asset else item.get("status", "pending")}
                for item in pending
            ])

            if asset == "correlation-rules":
                from ..platform_admin.copy import copy_correlation_rules_to_tenant

                result = copy_correlation_rules_to_tenant(
                    source_profile,
                    target_profile,
                    item_ids,
                    overwrite=overwrite,
                    stop_on_conflict=stop_on_conflict,
                    name_suffix=name_suffix,
                    on_progress=on_progress,
                )
            else:
                result = copy_assets_to_tenant(
                    source_profile,
                    target_profile,
                    asset,  # type: ignore[arg-type]
                    item_ids,
                    overwrite=overwrite,
                    stop_on_conflict=stop_on_conflict,
                    name_suffix=name_suffix,
                    prefer_direct_on_xsoar6=prefer_direct_on_xsoar6,
                    on_progress=on_progress,
                )

            asset_results[asset] = result
            step["status"] = "completed" if result.get("executed") else "failed"
            progress.mark_completed({"asset": asset, "executed": result.get("executed")})

            if not result.get("executed"):
                halted = True
                halt_reason = result.get("error") or f"failed on {asset}"
                if stop_on_conflict:
                    break

        progress.set_current(status="finished", halted=halted)

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "executed": not halted,
        "halted": halted,
        "halt_reason": halt_reason,
        "assets": asset_results,
    }
