"""Integration bundle export helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.integrations.bundle_helpers import (
    assert_exportable_integration,
    get_configuration_for_bundle,
)


@patch("cortex_ps_toolkit.integrations.bundle_helpers._lookup_body")
@patch("cortex_ps_toolkit.integrations.bundle_helpers._configuration_bodies")
@patch("cortex_ps_toolkit.integrations.bundle_helpers.get_profile")
def test_get_configuration_for_bundle_keeps_script_body(
    mock_get_profile: MagicMock,
    mock_bodies: MagicMock,
    mock_lookup: MagicMock,
) -> None:
    mock_get_profile.return_value = MagicMock(slug="lab")
    mock_bodies.return_value = {}
    mock_lookup.return_value = {
        "id": "MyCustom",
        "name": "MyCustom",
        "system": False,
        "integrationScript": {"script": "def main(): pass", "type": "python"},
    }
    doc = get_configuration_for_bundle("lab", "MyCustom")
    assert doc["integrationScript"]["script"] == "def main(): pass"
    assert_exportable_integration(doc)
