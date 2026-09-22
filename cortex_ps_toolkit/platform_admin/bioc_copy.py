"""Cross-tenant copy for BIOCs."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_action, op_info
from ..platforms import assert_operation_supported
from . import api
from .plan import plan_bioc_copy
from .service import refresh_section_cache
from .types import OPERATION_BY_SECTION


def copy_biocs_to_tenant(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    bioc_names: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["biocs"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["biocs"], target.tenant_type)

    progress = make_batch_copy_progress(
        title="BIOC Copy Progress",
        operation="platform_admin.bioc_copy",
        on_progress=on_progress,
    )
    with op_action("BIOC copy %s → %s (%d rule(s))", source.slug, target.slug, len(bioc_names)):
        plan = plan_bioc_copy(
            source,
            target,
            bioc_names,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
            name_suffix=name_suffix,
        )
        progress.complete_stage()
        entries = plan["entries"]
        if plan.get("has_conflicts"):
            return {**plan, "executed": False, "error": "conflicts detected (stop_on_conflict)"}

        results: list[dict[str, Any]] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            action = entry.get("action")
            if action in ("skip", "missing"):
                results.append({**entry, "status": "skipped"})
                continue
            source_bioc = api.get_bioc(source, str(entry["source_name"]))
            if not source_bioc:
                results.append({**entry, "status": "skipped", "error": "source missing"})
                continue
            name = str(entry.get("target_name") or entry.get("source_name") or "")
            emit_copy_item_step(
                on_progress,
                source=source.slug,
                target=target.slug,
                item_label="bioc",
                name=name,
                index=index,
                total=total,
            )
            op_info(
                "Copying BIOC %r (%d/%d) %s → %s",
                name,
                index,
                total,
                source.slug,
                target.slug,
            )
            write_doc = api.prepare_bioc_write(source_bioc, new_name=str(entry["target_name"]))
            _, status = api.insert_biocs(target, [write_doc])
            results.append({**entry, "status": status})

        progress.complete_stage()
        op_info("Refreshing BIOCs cache on %s after copy", target.slug)
        refresh_section_cache(target, "biocs")
        progress.complete_stage()
        return {
            **plan,
            "results": results,
            "executed": True,
        }
