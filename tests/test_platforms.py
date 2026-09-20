from __future__ import annotations

import pytest

from cortex_ps_toolkit.platforms import (
    Platform,
    SupportLevel,
    assert_operation_supported,
    get_operation,
    parse_platform,
    UnsupportedOperation,
)


def test_parse_platform_aliases() -> None:
    assert parse_platform("xsoar8") == Platform.XSOAR8
    assert parse_platform("xdr5") == Platform.XDR5
    assert parse_platform("agentix") == Platform.AGENTIX


def test_xql_run_not_on_xsoar6_or_xsoar8() -> None:
    spec = get_operation("xql.run")
    assert spec.support_level(Platform.XSIAM) == SupportLevel.DOCUMENTED
    assert spec.support_level(Platform.XSOAR8) == SupportLevel.UNSUPPORTED
    assert spec.support_level(Platform.XSOAR6) == SupportLevel.UNSUPPORTED
    with pytest.raises(UnsupportedOperation):
        assert_operation_supported("xql.run", Platform.XSOAR6)
    with pytest.raises(UnsupportedOperation):
        assert_operation_supported("xql.run", Platform.XSOAR8)


def test_playbook_cache_documented_on_xsoar8() -> None:
    spec = get_operation("cache.playbooks.refresh")
    assert spec.is_available(Platform.XSOAR8)
    assert spec.is_available(Platform.XSIAM)
