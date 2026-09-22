"""Unit tests for saved Object Setup bundle presets."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cortex_ps_toolkit.design_content import bundle_presets as bp


@pytest.fixture(autouse=True)
def _isolate_bundles_path(tmp_path, monkeypatch):
    path = tmp_path / "object_setup_bundles.json"
    monkeypatch.setattr(bp, "BUNDLES_PATH", path)
    yield path


@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
def test_save_and_list_bundle_preset_scoped_by_source(mock_profile) -> None:
    mock_profile.return_value.slug = "lab-source"
    entry = bp.save_bundle_preset(
        name="Phishing workflow",
        source_profile="lab-source",
        items=[{"asset": "incident-fields", "id": "abc", "name": "Custom Alert"}],
    )
    assert entry["id"] == "Phishing-workflow"
    assert entry["name"] == "Phishing workflow"
    listed = bp.list_bundle_presets(source_profile="lab-source")
    assert len(listed) == 1
    assert listed[0]["name"] == "Phishing workflow"
    assert bp.list_bundle_presets(source_profile="other-tenant") == []


@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
def test_same_identifier_overwrites_on_same_tenant(mock_profile) -> None:
    mock_profile.return_value.slug = "lab-source"
    bp.save_bundle_preset(
        name="My bundle",
        source_profile="lab-source",
        items=[{"asset": "incident-fields", "id": "a", "name": "A"}],
    )
    bp.save_bundle_preset(
        name="My bundle",
        source_profile="lab-source",
        items=[{"asset": "incident-fields", "id": "b", "name": "B"}],
    )
    listed = bp.list_bundle_presets(source_profile="lab-source")
    assert len(listed) == 1
    assert listed[0]["items"][0]["id"] == "b"


@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
def test_migrate_v1_flat_bundles(mock_profile) -> None:
    mock_profile.return_value.slug = "lab-source"
    from cortex_ps_toolkit.collections import save_collection

    save_collection(
        bp.BUNDLES_PATH,
        {
            "version": 1,
            "bundles": [
                {
                    "id": "uuid-old",
                    "name": "Legacy",
                    "application": "App",
                    "source_profile": "lab-source",
                    "items": [{"asset": "layouts", "id": "1", "name": "L"}],
                },
            ],
        },
    )
    rows = bp.list_bundle_presets(source_profile="lab-source")
    assert len(rows) == 1
    assert rows[0]["id"] == "uuid-old"


@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
@patch("cortex_ps_toolkit.design_content.bundle_presets.list_cached_items")
def test_resolve_bundle_items_by_name(mock_list, mock_profile) -> None:
    mock_profile.return_value.slug = "lab-source"
    mock_list.return_value = [
        {"id": "new-uuid", "name": "Custom Alert", "type": "shortText"},
    ]
    result = bp.resolve_bundle_items(
        "lab-source",
        [{"asset": "incident-fields", "id": "old-uuid", "name": "Custom Alert"}],
    )
    assert result["resolved_count"] == 1
    assert result["items"][0]["id"] == "new-uuid"
    assert not result["missing"]
