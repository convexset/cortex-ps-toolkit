from __future__ import annotations

from cortex_ps_toolkit.design_content.representation import diff_design_assets


def test_diff_layout_ignores_identity_and_metadata() -> None:
    expected = {"id": "1", "name": "Layout A", "description": "x", "version": 1, "prevName": "old"}
    actual = {"id": "2", "name": "Layout B", "description": "x", "version": 3}
    diff = diff_design_assets(expected, actual, "layouts")
    assert diff.equal is True


def test_diff_classifier_detects_body_change() -> None:
    expected = {"id": "1", "name": "C", "mapping": {"a": 1}}
    actual = {"id": "2", "name": "D", "mapping": {"a": 2}}
    diff = diff_design_assets(expected, actual, "classifiers")
    assert diff.equal is False
    assert "mapping" in diff.diff_keys
