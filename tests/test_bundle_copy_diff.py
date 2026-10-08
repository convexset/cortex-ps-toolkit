"""Bundle copy post-copy diff aggregation."""

from __future__ import annotations

from cortex_ps_toolkit.content.post_copy_diff import (
    aggregate_copy_diff_report,
    finalize_bundle_copy_diff_metadata,
)


def test_aggregate_copy_diff_report_flattens_bundle_phases() -> None:
    bundle_result = {
        "operation": "bundles.copy",
        "results": {
            "scripts": {
                "results": [
                    {
                        "name": "A",
                        "status": "copied",
                        "post_copy_diff": {
                            "kind": "script",
                            "outcome": "match",
                            "flagged_count": 0,
                            "ignored_count": 1,
                        },
                    },
                ],
            },
            "playbooks": {
                "copy_diff_report": {
                    "rows": [
                        {
                            "name": "PB1",
                            "status": "updated",
                            "post_copy_diff": {
                                "kind": "playbook",
                                "outcome": "mismatch",
                                "flagged_count": 2,
                                "ignored_count": 0,
                            },
                        },
                    ],
                },
            },
        },
    }
    report = aggregate_copy_diff_report(bundle_result)
    assert report["row_count"] == 2
    names = {row["name"] for row in report["rows"]}
    assert "scripts: A" in names
    assert "playbooks: PB1" in names
    assert report["flagged_delta_total"] == 2
    assert report["ignored_delta_total"] == 1


def test_finalize_bundle_copy_diff_metadata_merges_summaries() -> None:
    out: dict = {
        "post_copy_diff": True,
        "results": {
            "scripts": {
                "post_copy_diff_summary": {
                    "matched": 1,
                    "mismatched": 0,
                    "errors": 0,
                    "ignored_only": 0,
                },
            },
            "lists": {
                "post_copy_diff_summary": {
                    "matched": 2,
                    "mismatched": 1,
                    "errors": 0,
                    "ignored_only": 1,
                },
            },
        },
    }
    finalize_bundle_copy_diff_metadata(out)
    assert out["post_copy_diff_summary"]["matched"] == 3
    assert out["post_copy_diff_summary"]["mismatched"] == 1
    assert out["post_copy_diff_summary"]["ignored_only"] == 1
    assert out["copy_diff_report"]["row_count"] == 0
