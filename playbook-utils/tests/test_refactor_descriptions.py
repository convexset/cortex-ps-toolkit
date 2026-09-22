from __future__ import annotations

from playbook_utils.refactor_descriptions import (
    build_parent_description,
    build_refactor_metrics_log,
    build_sub_description,
    collect_extraction_metas,
    descriptions_for_refactor,
    embed_sub_playbook_description_on_job,
    httpv2_refs_from_post_result,
)


def _leaf_meta() -> dict:
    return {
        "kind": "root",
        "original_task_id": "372",
        "subplaybook_name": "[REFACTOR-S] Main [LEAF from 372]",
        "removed_task_ids": ["372", "373", "374"],
        "incoming_replacements": 2,
    }


def _cluster_meta() -> dict:
    return {
        "kind": "cluster",
        "start_task_id": "21",
        "end_task_id": "52",
        "subplaybook_name": "[REFACTOR-S] Main [INT from 21 to 52]",
        "removed_task_ids": ["21", "22", "52"],
        "incoming_replacements": 1,
        "end_outgoing": [{"source_id": "52", "label": "#none#", "target_id": "60"}],
    }


def test_collect_extraction_metas_combined() -> None:
    refactor = {
        "cluster_extractions": [_cluster_meta()],
        "extractions": [_leaf_meta()],
    }
    metas = collect_extraction_metas(refactor)
    assert len(metas) == 2
    assert metas[0]["kind"] == "cluster"
    assert metas[1]["kind"] == "root"


def test_parent_description_includes_httpv2_sub_playbook_names() -> None:
    metas = [_cluster_meta(), _leaf_meta()]
    httpv2_refs = httpv2_refs_from_post_result(
        {
            "outcomes": [
                {
                    "playbook_name": "[REFACTOR-S] Main [LEAF from 372]",
                    "ok": True,
                    "error_updates": [
                        {"task_id": "373", "retry_count": 20, "retry_interval": 30},
                        {"task_id": "372", "retry_count": 20, "retry_interval": 30},
                    ],
                }
            ]
        }
    )
    text = build_parent_description(
        source_name="Main",
        source_description="",
        metas=metas,
        httpv2_refs=httpv2_refs,
        post_specs=["contains:HttpV2:i|retry=20x30,stop-on-error"],
    )
    assert "Automatic Refactor of Main:" in text
    assert "Cluster Refactor from Task 21 to Task 52" in text
    assert "Leaf Refactor from Task 372" in text
    assert "HTTPv2 Task On Error Configuration Set: Up to 20 retries with retry interval 30 seconds" in text
    assert "    * Task 372 ([REFACTOR-S] Main [LEAF from 372])" in text
    assert "    * Task 373 ([REFACTOR-S] Main [LEAF from 372])" in text
    assert "Refactor Metrics:" in text
    assert " - 6 nodes moved" in text
    assert " - 2 call nodes added" in text
    assert " - 3 incoming links re-written" in text
    assert " - 1 outgoing links re-written" in text
    assert "[REFACTOR-S] Main [INT from 21 to 52]:" not in text

    metrics = build_refactor_metrics_log(source_name="Main", metas=metas)
    assert metrics.startswith("Refactor Metrics for Main:")
    assert "[REFACTOR-S] Main [INT from 21 to 52]:" in metrics
    assert "Totals: 6 nodes moved; 2 call nodes added" in metrics


def test_sub_description_uses_task_numbers_only_for_httpv2() -> None:
    meta = _leaf_meta()
    httpv2_refs = httpv2_refs_from_post_result(
        {
            "outcomes": [
                {
                    "playbook_name": meta["subplaybook_name"],
                    "ok": True,
                    "error_updates": [
                        {"task_id": "373", "retry_count": 20, "retry_interval": 30},
                    ],
                }
            ]
        }
    )
    text = build_sub_description(
        source_name="Main",
        meta=meta,
        httpv2_refs=httpv2_refs,
    )
    assert text.startswith("Refactored from Main")
    assert "Leaf Refactor from Task 372" in text
    assert "    * Task 373" in text
    assert "[REFACTOR-S]" not in text.split("HTTPv2", 1)[-1]


def test_embed_sub_playbook_description_on_job_sets_playbook_level_field() -> None:
    meta = _leaf_meta()
    sub = {
        "name": meta["subplaybook_name"],
        "_refactor": meta,
        "tasks": {
            "373": {
                "id": "373",
                "type": "regular",
                "task": {
                    "id": "373",
                    "name": "HttpV2 | Example",
                    "scriptName": "HttpV2",
                    "type": "regular",
                },
            }
        },
    }
    job = {"subplaybook_name": meta["subplaybook_name"], "sub": sub}
    text = embed_sub_playbook_description_on_job(
        source={"name": "Main"},
        job=job,
        post_specs=["contains:HttpV2:i|retry=20x30,stop-on-error"],
    )
    assert sub["description"] == text
    assert "Refactored from Main" in text
    assert "    * Task 373" in text
    assert "comment" not in sub


def test_parent_description_preserves_existing_source_description() -> None:
    payload = descriptions_for_refactor(
        source={"name": "Main", "description": "Original notes"},
        refactor={"extractions": [_leaf_meta()]},
    )
    text = payload["parent_description"]
    assert text.startswith("Original notes")
    assert "---" in text
    assert "Automatic Refactor of Main:" in text
    assert "Refactor Metrics:" in text
    assert " - 3 nodes moved" in text
    assert "[REFACTOR-S]" not in text.split("Refactor Metrics:", 1)[1]
    assert "Totals:" in payload["metrics_log"]
