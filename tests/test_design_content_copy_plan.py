from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.design_content.copy import plan_asset_copy
from cortex_ps_toolkit.design_content.types import AssetKind


def _profile(slug: str, platform: str):
    from cortex_ps_toolkit.credentials import CredentialProfile

    return CredentialProfile.from_storage_dict({
        "slug": slug,
        "label": slug,
        "url": "https://tenant.example.test",
        "key": "k",
        "id": "1",
        "tenant_type": platform,
        "verify_ssl": True,
    })


@patch("cortex_ps_toolkit.design_content.copy.refresh_asset_cache")
@patch("cortex_ps_toolkit.design_content.copy.get_item_body")
@patch("cortex_ps_toolkit.design_content.copy._cached_target_ids")
def test_plan_copy_assigns_bundle_for_cloud_target(
    mock_ids: object,
    mock_body: object,
    mock_refresh: object,
) -> None:
    mock_ids.return_value = set()
    mock_body.return_value = {"id": "Layout A", "name": "Layout A", "details": {}}
    source = _profile("x6", "xsoar6")
    target = _profile("xsiam", "xsiam")
    plan = plan_asset_copy(source, target, "layouts", ["Layout A"])
    entry = plan["entries"][0]
    assert entry["action"] == "copy"
    assert entry["write_method"] == "bundle"


@patch("cortex_ps_toolkit.design_content.copy.refresh_asset_cache")
@patch("cortex_ps_toolkit.design_content.copy.get_item_body")
@patch("cortex_ps_toolkit.design_content.copy._cached_target_ids")
def test_plan_copy_cross_tenant_keeps_source_id(
    mock_ids: object,
    mock_body: object,
    mock_refresh: object,
) -> None:
    mock_ids.return_value = set()
    mock_body.return_value = {
        "id": "SampleMirror Description",
        "name": "SampleMirror Description",
        "cliName": "samplemirrorDescription",
    }
    source = _profile("x6", "xsoar6")
    target = _profile("xsiam", "xsiam")
    plan = plan_asset_copy(source, target, "incident-fields", ["SampleMirror Description"])
    entry = plan["entries"][0]
    assert entry["target_id"] == "SampleMirror Description"
    assert entry["target_name"] == "SampleMirror Description"


@patch("cortex_ps_toolkit.design_content.copy.refresh_asset_cache")
@patch("cortex_ps_toolkit.design_content.copy.get_item_body")
@patch("cortex_ps_toolkit.design_content.copy._cached_target_ids")
def test_plan_copy_same_tenant_uses_copy_suffix(
    mock_ids: object,
    mock_body: object,
    mock_refresh: object,
) -> None:
    mock_ids.return_value = set()
    mock_body.return_value = {
        "id": "SampleMirror Description",
        "name": "SampleMirror Description",
        "cliName": "samplemirrorDescription",
    }
    profile = _profile("x6", "xsoar6")
    plan = plan_asset_copy(profile, profile, "incident-fields", ["SampleMirror Description"])
    entry = plan["entries"][0]
    assert entry["target_id"] == "SampleMirror Description-copy"
    assert entry["target_name"] == "SampleMirror Description-copy"
