"""Expected API failures skip persistent error toasts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.core.client import TenantClient
from cortex_ps_toolkit.core.quiet_api_failures import quiet_expected_api_failure
from cortex_ps_toolkit.platforms import Platform


def _profile() -> MagicMock:
    profile = MagicMock()
    profile.slug = "lab"
    profile.host = "https://example.com"
    profile.key = "key"
    profile.verify_ssl = True
    profile.api_id = ""
    profile.tenant_type = Platform.XSOAR6
    return profile


@patch("cortex_ps_toolkit.core.client.op_error")
@patch("cortex_ps_toolkit.core.client.op_warn")
def test_quiet_context_avoids_op_error_on_http_failure(mock_warn, mock_error) -> None:
    client = TenantClient(_profile())
    response = MagicMock()
    response.ok = False
    response.status_code = 400
    response.json.return_value = {"id": "errOptimisticLock"}
    response.text = ""
    response.content = b"{}"

    with quiet_expected_api_failure():
        try:
            client._raise_for_status(response, "write incident type T")
        except Exception:
            pass

    mock_error.assert_not_called()
    mock_warn.assert_not_called()
