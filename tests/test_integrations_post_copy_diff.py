"""Post-copy diff on integration copy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.integrations.copy import copy_integrations_to_tenant


def _custom_configuration(*, name: str = "CustomInt") -> dict:
    return {
        "id": name,
        "name": name,
        "display": f"{name} Display",
        "category": "Utilities",
        "system": False,
        "integrationScript": {
            "script": "print('ok')",
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


@patch("cortex_ps_toolkit.integrations.copy.refresh_integrations_cache")
@patch("cortex_ps_toolkit.integrations.copy.apply_post_copy_diffs")
@patch("cortex_ps_toolkit.integrations.copy.api.upload_integration_yaml")
@patch("cortex_ps_toolkit.integrations.copy.fetch_search_bundle")
@patch("cortex_ps_toolkit.integrations.copy.get_profile")
def test_copy_integrations_runs_post_copy_diff(
    mock_get_profile,
    mock_fetch,
    mock_upload,
    mock_apply_diff,
    _mock_refresh,
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
    mock_upload.return_value = MagicMock(data={}, status_code=200)
    mock_apply_diff.return_value = {"matched": 1, "mismatched": 0, "errors": 0, "ignored_only": 0}

    result = copy_integrations_to_tenant(
        "src",
        "dst",
        ["CustomInt"],
        post_copy_diff=True,
    )

    assert result["post_copy_diff"] is True
    mock_apply_diff.assert_called_once()
    assert result["results"][0]["status"] == "copied"
    assert result.get("copy_diff_report")
