"""Bundle membership and export for integration definitions."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.bundles.copy import plan_bundle_copy
from cortex_ps_toolkit.bundles.export import build_bundle_zip_bytes
from cortex_ps_toolkit.design_content.bundle_presets import resolve_bundle_items


@patch("cortex_ps_toolkit.design_content.bundle_presets.find_configuration_in_cache")
@patch("cortex_ps_toolkit.design_content.bundle_presets.get_profile")
def test_resolve_bundle_items_integrations(mock_profile: MagicMock, mock_find: MagicMock) -> None:
    mock_profile.return_value = MagicMock(slug="src")
    mock_find.return_value = {
        "id": "uuid-1",
        "name": "MyCustomIntegration",
        "display": "My Custom",
    }
    result = resolve_bundle_items(
        "src",
        [{"asset": "integrations", "id": "MyCustomIntegration", "name": "My Custom"}],
    )
    assert result["missing_count"] == 0
    assert result["items"][0]["asset"] == "integrations"
    assert result["items"][0]["id"] == "MyCustomIntegration"


@patch("cortex_ps_toolkit.bundles.copy.resolve_bundle_items")
@patch("cortex_ps_toolkit.bundles.copy.plan_integrations_copy")
@patch("cortex_ps_toolkit.bundles.copy.get_profile")
def test_plan_bundle_copy_includes_integrations_phase(
    mock_get_profile: MagicMock,
    mock_plan_int: MagicMock,
    mock_resolve: MagicMock,
) -> None:
    mock_get_profile.return_value = MagicMock(slug="x")
    mock_resolve.return_value = {
        "missing_count": 0,
        "items": [{"asset": "integrations", "id": "MyInt", "name": "My Int"}],
    }
    mock_plan_int.return_value = {
        "items": [{"integration_id": "MyInt", "action": "copy"}],
        "counts": {"copy": 1},
        "would_abort": False,
    }
    plan = plan_bundle_copy(
        "src",
        "tgt",
        [{"asset": "integrations", "id": "MyInt"}],
        copy_mode="overwrite",
        rename_suffix="_x",
    )
    phases = [p["phase"] for p in plan["sub_plans"]]
    assert phases[0] == "integrations"
    mock_plan_int.assert_called_once()
    _args, kwargs = mock_plan_int.call_args
    assert set(kwargs.keys()) == {"overwrite", "stop_on_conflict"}
    assert kwargs["overwrite"] is True


@patch("cortex_ps_toolkit.bundles.export.get_profile")
@patch("cortex_ps_toolkit.bundles.export.resolve_export_items")
@patch("cortex_ps_toolkit.bundles.export.get_configuration_for_bundle")
@patch("cortex_ps_toolkit.bundles.export.configuration_to_yaml_text")
@patch("cortex_ps_toolkit.bundles.export.assert_exportable_integration")
def test_build_bundle_zip_integrations(
    mock_assert: MagicMock,
    mock_yaml: MagicMock,
    mock_get_conf: MagicMock,
    mock_resolve_items: MagicMock,
    mock_profile: MagicMock,
) -> None:
    mock_profile.return_value = MagicMock(slug="prof-a", tenant_type="xsoar6")
    mock_resolve_items.return_value = (
        [{"asset": "integrations", "id": "MyInt", "name": "My Int"}],
        {"bundle_id": None, "bundle_name": None},
    )
    mock_get_conf.return_value = {"name": "MyInt", "display": "My Int"}
    mock_yaml.return_value = "name: MyInt\n"
    mock_assert.return_value = None

    zip_bytes, _filename = build_bundle_zip_bytes(
        "prof-a",
        items=[{"asset": "integrations", "id": "MyInt"}],
    )
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        assert "integrations/manifest.json" in names
        yml_files = [n for n in names if n.startswith("integrations/") and n.endswith(".yml")]
        assert len(yml_files) == 1
        manifest = json.loads(archive.read("bundle-manifest.json"))
        assert manifest["sections"]["integrations"] == 1
