from __future__ import annotations

from unittest.mock import patch

import pytest

from cortex_ps_toolkit.playbooks.refactor_cleanup import clear_refactor_playbooks, find_refactor_playbook_ids
from cortex_ps_toolkit.playbooks.refactor_presets import get_refactor_preset, list_refactor_presets


def test_list_refactor_presets_includes_mfec() -> None:
    presets = list_refactor_presets()
    ids = {preset["id"] for preset in presets}
    assert "mfec-uat-splunk-phishing" in ids
    assert "mfec-uat-full-workflow" in ids


def test_get_refactor_preset_splunk() -> None:
    preset = get_refactor_preset("mfec-uat-splunk-phishing")
    assert preset["profile"] == "mfec-uat"
    assert preset["playbook_name"] == "[Splunk] Phishing Email Reported by User"
    assert "366" in preset["leaf_tasks"]


@patch("cortex_ps_toolkit.playbooks.refactor_cleanup.list_cached_playbooks")
def test_find_refactor_playbook_ids(mock_list) -> None:
    mock_list.return_value = [
        {"id": "1", "name": "[REFACTOR-M] Main"},
        {"id": "2", "name": "Original"},
    ]
    matches = find_refactor_playbook_ids("mfec-uat", force_refresh=False)
    assert len(matches) == 1
    assert matches[0]["name"].startswith("[REFACTOR-")


@patch("cortex_ps_toolkit.playbooks.refactor_cleanup.delete_playbooks")
@patch("cortex_ps_toolkit.playbooks.refactor_cleanup.find_refactor_playbook_ids")
def test_clear_refactor_playbooks_dry_run(mock_find, mock_delete) -> None:
    mock_find.return_value = [{"id": "1", "name": "[REFACTOR-M] Main"}]
    result = clear_refactor_playbooks("mfec-uat", dry_run=True)
    assert result["dry_run"] is True
    assert result["count"] == 1
    mock_delete.assert_not_called()
