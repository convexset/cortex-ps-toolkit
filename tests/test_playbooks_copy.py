from __future__ import annotations

from unittest.mock import patch

import pytest

from cortex_ps_toolkit.playbooks.copy import (
    _classify_copy_action,
    copy_playbooks_to_tenant,
    plan_playbooks_copy,
)


@pytest.mark.parametrize(
    ("existing", "overwrite", "stop_on_conflict", "expected"),
    [
        (None, False, False, "copy"),
        ({"id": "2"}, False, False, "skip"),
        ({"id": "2"}, True, False, "update"),
        ({"id": "2"}, False, True, "conflict"),
    ],
)
def test_classify_copy_action(existing, overwrite, stop_on_conflict, expected) -> None:
    assert (
        _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        == expected
    )


@patch("cortex_ps_toolkit.playbooks.copy.refresh_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy.find_playbook_in_index")
@patch("cortex_ps_toolkit.playbooks.copy.resolve_playbook_meta")
@patch("cortex_ps_toolkit.playbooks.copy.get_profile")
def test_plan_playbooks_copy_conflict(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_refresh,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {"id": "pb1", "name": "Main PB"}
    mock_find_target.return_value = {"id": "existing", "name": "Main PB"}

    plan = plan_playbooks_copy("src", "dst", ["pb1"], stop_on_conflict=True)
    assert plan["would_abort"] is True
    assert plan["counts"]["conflict"] == 1


@patch("cortex_ps_toolkit.playbooks.copy.save_playbook_document")
@patch("cortex_ps_toolkit.playbooks.copy.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.copy.refresh_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy.find_playbook_in_index")
@patch("cortex_ps_toolkit.playbooks.copy.resolve_playbook_meta")
@patch("cortex_ps_toolkit.playbooks.copy.get_profile")
def test_copy_playbooks_to_tenant(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_refresh,
    mock_get_playbook,
    mock_save_document,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {"id": "pb1", "name": "Main PB"}
    mock_find_target.return_value = None
    mock_get_playbook.return_value = {"id": "pb1", "name": "Main PB", "tasks": {}}
    mock_save_document.return_value = ({"id": "new-id"}, 200, [])

    result = copy_playbooks_to_tenant("src", "dst", ["pb1"])
    assert result["results"][0]["status"] == "copied"
    mock_save_document.assert_called_once()
    assert mock_save_document.call_args.kwargs["overwrite"] is False
    assert mock_save_document.call_args.kwargs["source_profile"] is source


@patch("cortex_ps_toolkit.playbooks.copy.save_playbook_document")
@patch("cortex_ps_toolkit.playbooks.copy.api.get_playbook")
@patch("cortex_ps_toolkit.playbooks.copy.refresh_playbooks_cache")
@patch("cortex_ps_toolkit.playbooks.copy.find_playbook_in_index")
@patch("cortex_ps_toolkit.playbooks.copy.resolve_playbook_meta")
@patch("cortex_ps_toolkit.playbooks.copy.get_profile")
def test_copy_playbooks_to_tenant_overwrite(
    mock_get_profile,
    mock_resolve_meta,
    mock_find_target,
    mock_refresh,
    mock_get_playbook,
    mock_save_document,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": "xsoar6"})()
    target = type("P", (), {"slug": "dst", "tenant_type": "xsoar6"})()
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    mock_resolve_meta.return_value = {"id": "pb1", "name": "Main PB"}
    mock_find_target.return_value = {"id": "existing-id", "name": "Main PB"}
    mock_get_playbook.return_value = {"id": "pb1", "name": "Main PB", "tasks": {}}
    mock_save_document.return_value = ({"id": "existing-id"}, 200, [])

    result = copy_playbooks_to_tenant("src", "dst", ["pb1"], overwrite=True)
    assert result["results"][0]["status"] == "updated"
    mock_save_document.assert_called_once_with(
        target,
        {"id": "pb1", "name": "Main PB", "tasks": {}},
        filename="Main PB.yml",
        target_playbook_id="existing-id",
        overwrite=True,
        source_profile=source,
    )
