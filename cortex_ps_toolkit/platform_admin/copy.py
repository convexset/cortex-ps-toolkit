"""Cross-tenant copy for correlation rules."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.batch_copy_progress import emit_copy_item_step, make_batch_copy_progress
from ..credentials import CredentialProfile, get_profile
from ..ops_log import op_action, op_info
from ..content.post_copy_diff import (
    COMPARE_MODE,
    POST_COPY_DIFF_PROBE_ID,
    aggregate_copy_diff_report,
    new_copy_run_telemetry,
    summary_from_copy_diff_report,
)
from ..content.representation import diff_representations_classified
from ..design_content.copy_progress import notify_item_copied
from ..platforms import assert_operation_supported
from . import api
from .plan import plan_correlation_copy
from .service import refresh_section_cache
from .types import OPERATION_BY_SECTION


def copy_correlation_rules_to_tenant(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    rule_names: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
    post_copy_diff: bool = False,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], source.tenant_type)
    assert_operation_supported(OPERATION_BY_SECTION["correlation-rules"], target.tenant_type)

    progress = make_batch_copy_progress(
        title="Correlation Rules Copy Progress",
        operation="platform_admin.correlation_copy",
        on_progress=on_progress,
    )
    with op_action(
        "Correlation rules copy %s → %s (%d rule(s))",
        source.slug,
        target.slug,
        len(rule_names),
    ):
        plan = plan_correlation_copy(
            source,
            target,
            rule_names,
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
            source_rule = api.get_correlation_rule(source, str(entry["source_name"]))
            if not source_rule:
                results.append({**entry, "status": "skipped", "error": "source missing"})
                continue
            name = str(entry.get("target_name") or entry.get("source_name") or "")
            emit_copy_item_step(
                on_progress,
                source=source.slug,
                target=target.slug,
                item_label="correlation rule",
                name=name,
                index=index,
                total=total,
            )
            op_info(
                "Copying correlation rule %r (%d/%d) %s → %s",
                name,
                index,
                total,
                source.slug,
                target.slug,
            )
            write_doc = api.prepare_correlation_write(source_rule, new_name=str(entry["target_name"]))
            _, status = api.insert_correlation_rules(target, [write_doc])
            result_entry = {**entry, "status": status}
            results.append(result_entry)
            notify_item_copied(on_progress, "correlation-rules", result_entry)

        progress.complete_stage()
        op_info("Refreshing correlation rules cache on %s after copy", target.slug)
        refresh_section_cache(target, "correlation-rules")
        progress.complete_stage()
        out: dict[str, Any] = {
            **plan,
            "results": results,
            "executed": True,
            "post_copy_diff": post_copy_diff,
        }
        if post_copy_diff:
            for row in results:
                status = row.get("status")
                if status in ("skipped", "missing") or row.get("action") in ("skip", "missing"):
                    continue
                if isinstance(status, int) and not (200 <= status < 300):
                    continue
                source_name = str(row.get("source_name") or "")
                target_name = str(row.get("target_name") or source_name)
                source_rule = api.get_correlation_rule(source, source_name)
                if not source_rule:
                    continue
                expected = api.prepare_correlation_write(source_rule, new_name=target_name)
                read_back = api.get_correlation_rule(target, target_name)
                if not read_back:
                    payload = {
                        "probe": POST_COPY_DIFF_PROBE_ID,
                        "compare_mode": COMPARE_MODE,
                        "kind": "document",
                        "item_name": target_name,
                        "equal": False,
                        "outcome": "error",
                        "error": "correlation rule not found on target after copy",
                        "error_code": "READ_BACK_MISSING",
                        "flagged": [],
                        "ignored": [],
                        "differences": [],
                        "flagged_count": 0,
                        "ignored_count": 0,
                    }
                else:
                    classified = diff_representations_classified(expected, read_back, "document")
                    payload = classified.to_dict()
                    payload.update({
                        "probe": POST_COPY_DIFF_PROBE_ID,
                        "compare_mode": COMPARE_MODE,
                        "kind": "document",
                        "item_name": target_name,
                        "outcome": (
                            "mismatch"
                            if payload.get("flagged")
                            else ("match_ignored_delta" if payload.get("ignored") else "match")
                        ),
                    })
                upload_status = "updated" if row.get("action") == "update" else "copied"
                payload["upload_status"] = upload_status
                row["name"] = target_name
                row["post_copy_diff"] = payload
            out["telemetry"] = new_copy_run_telemetry(
                operation="platform_admin.correlation_copy",
                post_copy_diff=True,
            )
            out["copy_diff_report"] = aggregate_copy_diff_report(out)
            out["post_copy_diff_summary"] = summary_from_copy_diff_report(out["copy_diff_report"])
            out["post_copy_diff_summary"]["probe"] = POST_COPY_DIFF_PROBE_ID
        return out
