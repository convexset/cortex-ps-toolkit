"""Unit tests for deep copy sub-playbook binding map helpers."""

from cortex_ps_toolkit.playbooks.copy_components import (
    _build_copy_stage_labels,
    _merge_remap_into_binding_maps,
)


def test_merge_remap_uses_source_names_when_target_index_lacks_name() -> None:
    name_to_id: dict[str, str] = {}
    id_to_name: dict[str, str] = {}
    playbook_id_remap = {"src-a": "tgt-a"}
    source_names = {"src-a": "[REFACTOR-S] Example"}

    _merge_remap_into_binding_maps(name_to_id, id_to_name, playbook_id_remap, source_names)

    assert name_to_id["[REFACTOR-S] Example"] == "tgt-a"
    assert id_to_name["tgt-a"] == "[REFACTOR-S] Example"
    assert id_to_name["src-a"] == "[REFACTOR-S] Example"


def test_build_copy_stage_labels_includes_waves() -> None:
    plan = {
        "analysis_summary": {"script_ids": ["s1"]},
        "execution_plan": {"playbook_waves": [["p1"], ["p2", "p3"]]},
    }
    labels = _build_copy_stage_labels(plan)
    assert labels[0] == "Parallel Script Copy"
    assert any("Wave 1" in label for label in labels)
    assert any("Wave 2" in label for label in labels)
    assert labels[-1] == "Final Playbook Cache Refresh"
