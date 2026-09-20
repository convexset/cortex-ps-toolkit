from __future__ import annotations

from cortex_ps_toolkit.core.paths import (
    uses_cortex_platform_content_api,
    xsoar_shaped_path,
    xsoar_shaped_url,
)
from cortex_ps_toolkit.platforms import Platform, SupportLevel, get_operation


def test_xsoar8_keeps_public_v1_prefix() -> None:
    assert xsoar_shaped_path(Platform.XSOAR8, "/lists") == "/xsoar/public/v1/lists"


def test_xsoar6_strips_public_v1_prefix() -> None:
    assert xsoar_shaped_path(Platform.XSOAR6, "/xsoar/public/v1/lists") == "/lists"
    assert xsoar_shaped_path(Platform.XSOAR6, "/lists") == "/lists"


def test_xdr3_matches_xdr5_compat_path() -> None:
    for platform in (Platform.XDR3, Platform.XDR5):
        assert xsoar_shaped_path(platform, "/lists") == "/xsoar/public/v1/lists"
        assert xsoar_shaped_path(platform, "/lists/save") == "/xsoar/public/v1/lists/save"


def test_xsoar_shaped_url() -> None:
    url = xsoar_shaped_url("https://tenant.test", Platform.XSIAM, "/lists")
    assert url == "https://tenant.test/xsoar/public/v1/lists"


def test_cortex_platform_content_api_platforms() -> None:
    for platform in (Platform.XSIAM, Platform.XDR3, Platform.XDR5, Platform.AGENTIX):
        assert uses_cortex_platform_content_api(platform)
    assert not uses_cortex_platform_content_api(Platform.XSOAR8)


def test_copy_experimental_on_xdr5_and_agentix() -> None:
    for op_id in ("scripts.copy", "playbooks.copy"):
        spec = get_operation(op_id)
        assert spec.support_level(Platform.XDR5) == SupportLevel.EXPERIMENTAL
        assert spec.support_level(Platform.AGENTIX) == SupportLevel.EXPERIMENTAL
