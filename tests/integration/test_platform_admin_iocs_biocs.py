"""Live integration: IOC and BIOC insert→delete cycles on lab tenants."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.platforms import Platform, get_operation

from scripts.probe_iocs_biocs_lab import probe_bioc, probe_ioc

from tests.conftest import LAB_TENANT_BY_SLUG, LAB_TENANT_SLUGS

pytestmark = pytest.mark.integration


def _platform(slug: str) -> Platform:
    return LAB_TENANT_BY_SLUG[slug]


def _supported(operation_id: str, platform: Platform) -> bool:
    return get_operation(operation_id).is_available(platform)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_ioc_insert_delete_cycle(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    platform = _platform(slug)
    if not _supported("content.indicators.manage", platform):
        pytest.skip(f"IOCs unsupported on {platform.value}")

    profile = get_profile(slug)
    result = probe_ioc(profile)

    if result.get("error"):
        if platform == Platform.AGENTIX and "402" in str(result["error"]):
            pytest.skip("AgentiX IOC license inactive (402)")
        pytest.fail(f"IOC probe failed on {slug}: {result}")

    assert result.get("cycle_ok") is True, result


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_bioc_list_or_cycle(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    platform = _platform(slug)
    if not _supported("content.biocs.manage", platform):
        pytest.skip(f"BIOCs unsupported on {platform.value}")

    profile = get_profile(slug)
    result = probe_bioc(profile)

    if result.get("skipped"):
        pytest.skip(result.get("reason", "BIOCs skipped"))

    list_info = result.get("list") or {}
    if list_info.get("error"):
        if platform == Platform.AGENTIX and "402" in str(list_info["error"]):
            pytest.skip("AgentiX BIOC license inactive (402)")
        pytest.fail(f"BIOC list failed on {slug}: {list_info['error']}")

    insert_delete = result.get("insert_delete") or {}
    if insert_delete.get("skipped"):
        pytest.skip(insert_delete.get("reason", "no BIOCs to clone"))

    if result.get("error"):
        pytest.fail(f"BIOC probe failed on {slug}: {result}")

    assert result.get("cycle_ok") is True, result
    if result.get("insert_cycle_skipped"):
        assert (result.get("api_smoke") or {}).get("get_ok") is True
