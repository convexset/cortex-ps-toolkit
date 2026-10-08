from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.content.post_copy_diff import (
    POST_COPY_DIFF_PROBE_ID,
    post_copy_diff_payload,
)
from cortex_ps_toolkit.playbooks.copy import copy_playbooks_to_tenant


def test_post_copy_diff_payload_equal() -> None:
    target = type("P", (), {"slug": "dst"})()
    doc = {"name": "PB", "tasks": {}, "script": "x = 1"}
    payload = post_copy_diff_payload(
        source_doc=doc,
        target=target,
        target_entity_id="tid",
        kind="playbook",
        fetch=lambda _p, _id: dict(doc),
        item_name="PB",
    )
    assert payload["equal"] is True
    assert payload["differences"] == []
    assert payload["outcome"] == "match"
    assert payload["probe"] == POST_COPY_DIFF_PROBE_ID
    assert payload["read_back_fingerprint"] == "pb:tasks=0"


def test_post_copy_diff_payload_missing_target_id() -> None:
    target = type("P", (), {"slug": "dst"})()
    payload = post_copy_diff_payload(
        source_doc={"name": "PB", "tasks": {}},
        target=target,
        target_entity_id="",
        kind="playbook",
        fetch=lambda _p, _id: {},
        item_name="PB",
    )
    assert payload["outcome"] == "error"
    assert payload["error_code"] == "MISSING_TARGET_ID"


@patch("cortex_ps_toolkit.playbooks.copy.apply_post_copy_diffs")
@patch("cortex_ps_toolkit.playbooks.copy.save_playbook_document")
@patch("cortex_ps_toolkit.playbooks.copy.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.copy.refresh_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy.find_playbook_in_index")
@patch("cortex_ps_toolkit.playbooks.copy.resolve_playbook_meta")
@patch("cortex_ps_toolkit.playbooks.copy.get_profile")
def test_copy_playbooks_post_copy_diff(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_refresh,
    mock_get_playbook,
    mock_save_document,
    mock_apply_diff,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {"id": "pb1", "name": "Main PB"}
    mock_find_target.return_value = None
    mock_get_playbook.return_value = {"id": "pb1", "name": "Main PB", "tasks": {}}
    mock_save_document.return_value = ({"id": "new-id"}, 200, [])
    mock_apply_diff.return_value = {"matched": 1, "mismatched": 0, "errors": 0}

    result = copy_playbooks_to_tenant("src", "dst", ["pb1"], post_copy_diff=True)
    assert result["post_copy_diff"] is True
    assert result["post_copy_diff_summary"]["matched"] == 1
    mock_apply_diff.assert_called_once()
