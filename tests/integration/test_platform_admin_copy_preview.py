"""Integration: copy preview plans against live lab tenants (no writes)."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.platform_admin.plan import plan_bioc_copy, plan_indicator_copy
from cortex_ps_toolkit.platform_admin.service import list_cached_items, refresh_section_cache
from cortex_ps_toolkit.platforms import Platform, get_operation

from tests.conftest import LAB_TENANT_BY_SLUG, LAB_TENANT_SLUGS

pytestmark = pytest.mark.integration


def _supported(operation_id: str, platform: Platform) -> bool:
    return get_operation(operation_id).is_available(platform)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_indicator_copy_preview_same_tenant_skips_or_conflicts(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    platform = LAB_TENANT_BY_SLUG[slug]
    if not _supported("content.indicators.manage", platform):
        pytest.skip(f"IOCs unsupported on {platform.value}")

    refresh_section_cache(slug, "indicators")
    items = list_cached_items(slug, "indicators")
    if not items:
        pytest.skip("No cached indicators — refresh first")

    indicator_id = str(items[0].get("id") or "")
    if not indicator_id:
        pytest.skip("Cached indicator missing id")

    plan = plan_indicator_copy(slug, slug, [indicator_id], stop_on_conflict=True)
    assert plan["compatible"] is True
    assert plan["entries"]
    assert plan["entries"][0]["action"] in ("conflict", "skip", "update", "copy")


@pytest.mark.parametrize("slug", ["psojapac-xsiam", "cortex-cs-xdr5"])
def test_bioc_copy_preview_requires_distinct_target(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    platform = LAB_TENANT_BY_SLUG[slug]
    if not _supported("content.biocs.manage", platform):
        pytest.skip(f"BIOCs unsupported on {platform.value}")

    refresh_section_cache(slug, "biocs")
    items = list_cached_items(slug, "biocs")
    if not items:
        pytest.skip("No cached BIOCs")

    name = str(items[0].get("name") or "")
    if not name:
        pytest.skip("Cached BIOC missing name")

    other = "cortex-cs-xdr5" if slug == "psojapac-xsiam" else "psojapac-xsiam"
    if other not in available_lab_slugs:
        pytest.skip("Second cortex tenant not configured for cross-tenant preview")

    get_profile(other)
    plan = plan_bioc_copy(slug, other, [name])
    assert plan["entries"]
    assert plan["entries"][0]["action"] in ("copy", "skip", "update", "missing", "conflict")
