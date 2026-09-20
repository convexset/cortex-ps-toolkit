from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.integrations.copy import copy_integrations_to_tenant, plan_integrations_copy
from cortex_ps_toolkit.integrations.delete import delete_integrations, plan_integrations_delete
from cortex_ps_toolkit.integrations.metadata import is_copyable_integration, is_deletable_integration
from cortex_ps_toolkit.integrations.yaml_export import configuration_to_yaml_document


def _custom_configuration(*, name: str = "CustomInt", script: str = "print('ok')") -> dict:
    return {
        "id": name,
        "name": name,
        "display": f"{name} Display",
        "category": "Utilities",
        "system": False,
        "integrationScript": {
            "script": script,
            "type": "python",
            "subtype": "python3",
            "dockerImage": "demisto/python3:1.0.0",
            "commands": [],
        },
    }


def _profile(slug: str) -> MagicMock:
    profile = MagicMock()
    profile.slug = slug
    profile.tenant_type = "xsoar8"
    return profile


@patch("cortex_ps_toolkit.integrations.copy.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.copy.get_profile")
def test_plan_integrations_copy_skip_when_exists(mock_get_profile, mock_fetch) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    custom = _custom_configuration()
    mock_fetch.side_effect = [
        ({}, {"CustomInt": custom}, []),
        ({}, {"CustomInt": custom}, []),
    ]

    plan = plan_integrations_copy("src", "dst", ["CustomInt"], overwrite=False)
    assert plan["counts"]["skip"] == 1


@patch("cortex_ps_toolkit.integrations.copy.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.copy.get_profile")
def test_plan_integrations_copy_conflict(mock_get_profile, mock_fetch) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    custom = _custom_configuration()
    mock_fetch.side_effect = [
        ({}, {"CustomInt": custom}, []),
        ({}, {"CustomInt": custom}, []),
    ]

    plan = plan_integrations_copy("src", "dst", ["CustomInt"], stop_on_conflict=True)
    assert plan["would_abort"] is True
    assert plan["counts"]["conflict"] == 1


@patch("cortex_ps_toolkit.integrations.copy.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.copy.get_profile")
def test_plan_integrations_copy_blocks_pack_integration(mock_get_profile, mock_fetch) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    pack_item = _custom_configuration(name="PackInt")
    pack_item["packID"] = "SomePack"
    mock_fetch.side_effect = [
        ({}, {"PackInt": pack_item}, []),
        ({}, {}, []),
    ]

    plan = plan_integrations_copy("src", "dst", ["PackInt"])
    assert plan["counts"]["blocked"] == 1


@patch("cortex_ps_toolkit.integrations.delete.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.delete.get_profile")
def test_plan_integrations_delete_warns_on_instances(mock_get_profile, mock_fetch) -> None:
    profile = _profile("lab")
    mock_get_profile.return_value = profile
    custom = _custom_configuration()
    instances = [{"name": "CustomInt_instance_1", "brand": "CustomInt", "enabled": True}]
    mock_fetch.return_value = ({}, {"CustomInt": custom}, instances)

    plan = plan_integrations_delete("lab", ["CustomInt"])
    assert plan["would_delete"] is True
    assert plan["has_instance_warnings"] is True
    assert plan["warnings"][0]["instance_count"] == 1
    assert plan["items"][0]["action"] == "delete"


@patch("cortex_ps_toolkit.integrations.delete.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.delete.get_profile")
def test_plan_integrations_delete_blocks_system(mock_get_profile, mock_fetch) -> None:
    profile = _profile("lab")
    mock_get_profile.return_value = profile
    system = _custom_configuration(name="Core")
    system["system"] = True
    mock_fetch.return_value = ({}, {"Core": system}, [])

    plan = plan_integrations_delete("lab", ["Core"])
    assert plan["counts"]["blocked"] == 1
    assert plan["would_delete"] is False


def test_is_copyable_and_deletable_rules() -> None:
    custom = _custom_configuration()
    assert is_copyable_integration(custom) == (True, None)
    assert is_deletable_integration(custom) == (True, None)

    system = _custom_configuration(name="Core")
    system["system"] = True
    assert is_copyable_integration(system)[0] is False
    assert is_deletable_integration(system)[0] is False


def test_find_configuration_in_cache() -> None:
    from cortex_ps_toolkit.integrations.service import find_configuration_in_cache

    with patch("cortex_ps_toolkit.integrations.service.load_scope_cache") as mock_load:
        mock_load.return_value = {
            "configurations": [
                {"id": "CustomInt", "name": "CustomInt", "display": "Custom"},
            ],
        }
        found = find_configuration_in_cache("lab", "CustomInt")
        assert found is not None
        assert found["name"] == "CustomInt"
        assert find_configuration_in_cache("lab", "Missing") is None


def test_configuration_to_yaml_document_shape() -> None:
    document = configuration_to_yaml_document(_custom_configuration())
    assert document["name"] == "CustomInt"
    assert document["commonfields"]["id"] == "CustomInt"
    assert document["script"]["script"] == "print('ok')"


@patch("cortex_ps_toolkit.integrations.delete.api.delete_integration_configuration")
@patch("cortex_ps_toolkit.integrations.delete.refresh_integrations_cache")
@patch("cortex_ps_toolkit.integrations.delete.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.delete.get_profile")
def test_delete_integrations_refreshes_cache(
    mock_get_profile,
    mock_fetch,
    mock_refresh,
    mock_delete,
) -> None:
    profile = _profile("lab")
    mock_get_profile.return_value = profile
    custom = _custom_configuration()
    instances: list[dict] = []
    mock_fetch.side_effect = [
        ({}, {"CustomInt": custom}, instances),
        ({}, {"CustomInt": custom}, instances),
    ]
    mock_delete.return_value = MagicMock(data={}, status_code=200)

    result = delete_integrations("lab", ["CustomInt"])
    assert result["results"][0]["status"] == "deleted"
    mock_refresh.assert_called_once_with(profile)


@patch("cortex_ps_toolkit.integrations.copy.api.upload_integration_yaml")
@patch("cortex_ps_toolkit.integrations.copy.refresh_integrations_cache")
@patch("cortex_ps_toolkit.integrations.copy.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.copy.get_profile")
def test_copy_integrations_to_tenant_uploads_yaml(
    mock_get_profile,
    mock_fetch,
    mock_refresh,
    mock_upload,
) -> None:
    source = _profile("src")
    target = _profile("dst")
    mock_get_profile.side_effect = lambda slug: source if slug == "src" else target
    custom = _custom_configuration()
    mock_fetch.side_effect = [
        ({}, {"CustomInt": custom}, []),
        ({}, {}, []),
        ({}, {"CustomInt": custom}, []),
    ]
    mock_upload.return_value = MagicMock(data={"ok": True}, status_code=200)

    result = copy_integrations_to_tenant("src", "dst", ["CustomInt"], overwrite=True)
    assert result["results"][0]["status"] == "copied"
    mock_upload.assert_called_once()
