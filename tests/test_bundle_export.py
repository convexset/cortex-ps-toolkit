"""Unit tests for portable bundle ZIP export."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.bundles.export import (
    BundleExportError,
    build_bundle_zip_bytes,
    field_kind,
    plan_bundle_export,
    resolve_export_items,
)


def test_field_kind_prefixes() -> None:
    assert field_kind("generic_foo") == "generic"
    assert field_kind("evidence_bar") == "evidence"
    assert field_kind("incident_baz") == "incident"
    assert field_kind("custom") == "other"


@patch("cortex_ps_toolkit.bundles.export.resolve_bundle_items")
def test_resolve_export_items_missing(mock_resolve: MagicMock) -> None:
    mock_resolve.return_value = {"missing_count": 1, "missing": [{"asset": "lists", "id": "x"}]}
    with pytest.raises(BundleExportError) as exc:
        resolve_export_items("prof-a", items=[{"asset": "lists", "id": "x"}])
    assert exc.value.missing


@patch("cortex_ps_toolkit.bundles.export.resolve_bundle_items")
def test_plan_bundle_export_sections(mock_resolve: MagicMock) -> None:
    mock_resolve.return_value = {
        "missing_count": 0,
        "items": [
            {"asset": "lists", "id": "1", "name": "L1"},
            {"asset": "scripts", "id": "2", "name": "S1"},
        ],
    }
    plan = plan_bundle_export("prof-a", items=[{"asset": "lists", "id": "1"}])
    assert plan["ok"] is True
    assert plan["sections"]["lists"] == 1
    assert plan["sections"]["scripts"] == 1


@patch("cortex_ps_toolkit.bundles.export.get_profile")
@patch("cortex_ps_toolkit.bundles.export.resolve_export_items")
@patch("cortex_ps_toolkit.bundles.export.resolve_list_entry")
@patch("cortex_ps_toolkit.bundles.export.normalize_list_data")
@patch("cortex_ps_toolkit.bundles.export.build_portable_script_yaml")
@patch("cortex_ps_toolkit.bundles.export.find_script_in_index")
def test_build_bundle_zip_lists_and_scripts(
    mock_find_script: MagicMock,
    mock_yaml: MagicMock,
    mock_norm: MagicMock,
    mock_list_entry: MagicMock,
    mock_resolve_items: MagicMock,
    mock_profile: MagicMock,
) -> None:
    mock_profile.return_value = MagicMock(slug="prof-a", tenant_type="xsoar6")
    mock_resolve_items.return_value = (
        [
            {"asset": "lists", "id": "lid", "name": "My List"},
            {"asset": "scripts", "id": "sid", "name": "My Script"},
        ],
        {"bundle_id": None, "bundle_name": None},
    )
    mock_list_entry.return_value = {
        "name": "My List",
        "type": "plain_text",
        "description": "d",
        "data": "a\nb",
    }
    mock_norm.return_value = "a\nb"
    mock_find_script.return_value = {"name": "My Script"}
    mock_yaml.return_value = "name: My Script\nscript: |\n  return_results('ok')\n"

    zip_bytes, filename = build_bundle_zip_bytes(
        "prof-a",
        items=[
            {"asset": "lists", "id": "lid"},
            {"asset": "scripts", "id": "sid"},
        ],
        bundle_name="Test Export",
    )
    assert filename.endswith(".zip")
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        names = set(archive.namelist())
        assert "bundle-manifest.json" in names
        assert "lists/manifest.json" in names
        assert "scripts/manifest.json" in names
        manifest = json.loads(archive.read("bundle-manifest.json"))
        assert manifest["bundle_name"] == "Test Export"
        assert manifest["sections"]["lists"] == 1
        list_files = [n for n in names if n.startswith("lists/") and n.endswith(".txt")]
        assert len(list_files) == 1
        assert archive.read(list_files[0]).decode() == "a\nb"
