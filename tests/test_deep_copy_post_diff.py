from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.content.post_copy_diff import apply_deep_copy_post_diffs, merge_diff_summaries


def test_merge_diff_summaries() -> None:
    merged = merge_diff_summaries(
        {"matched": 2, "mismatched": 1, "errors": 0},
        {"matched": 1, "mismatched": 0, "errors": 1},
    )
    assert merged == {"matched": 3, "mismatched": 1, "errors": 1, "ignored_only": 0}


def test_apply_deep_copy_post_diffs_attaches_rows() -> None:
    target = type("P", (), {"slug": "dst"})()
    source = type("P", (), {"slug": "src"})()
    script_doc = {"name": "S", "type": "python", "script": "pass"}
    playbook_doc = {"name": "Main", "tasks": {}}
    script_results = [
        {"script_id": "s1", "name": "S", "status": "copied", "target_script_id": "t1"},
    ]
    playbook_results = [
        {"playbook_id": "p1", "name": "Main", "status": "copied", "target_playbook_id": "tp1"},
    ]

    summary = apply_deep_copy_post_diffs(
        source=source,
        target=target,
        script_results=script_results,
        playbook_results=playbook_results,
        playbook_source_docs={"p1": playbook_doc},
        fetch_script=lambda _p, _id: dict(script_doc),
        fetch_playbook=lambda _p, _id: dict(playbook_doc),
    )
    assert summary["total"]["matched"] == 2
    assert script_results[0]["post_copy_diff"]["equal"] is True
    assert playbook_results[0]["post_copy_diff"]["equal"] is True


def test_copy_components_passes_post_copy_diff_kwarg() -> None:
    from cortex_ps_toolkit.playbooks.copy_components import copy_playbook_components_to_tenant

    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    with patch(
        "cortex_ps_toolkit.playbooks.copy_components.get_profile",
        side_effect=lambda slug: source if slug == "src" else target,
    ), patch(
        "cortex_ps_toolkit.playbooks.copy_components.plan_playbook_components_copy",
        return_value={"would_abort": False, "playbooks": {"items": []}, "scripts": {}, "analysis_summary": {}},
    ), patch(
        "cortex_ps_toolkit.playbooks.copy_components._execute_playbook_components_copy",
        return_value={"script_results": [], "playbook_results": []},
    ) as mock_exec:
        copy_playbook_components_to_tenant("src", "dst", "root", post_copy_diff=True)
        assert mock_exec.call_args.kwargs["post_copy_diff"] is True
