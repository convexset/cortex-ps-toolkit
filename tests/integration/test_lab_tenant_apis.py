"""Live read-only / preview API tests against configured lab tenants.

Requires credential profiles from presets/credentials/lab-sources.json.
XDR 3 is excluded (no lab tenant). Run:

    pytest tests/integration -m integration -v

Or include in the full suite when credentials are present.
"""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.credentials_validate import validate_profile
from cortex_ps_toolkit.lists.delete import plan_lists_delete
from cortex_ps_toolkit.lists.service import refresh_lists_cache
from cortex_ps_toolkit.platforms import Platform, get_operation
from cortex_ps_toolkit.playbooks import api as playbooks_api
from cortex_ps_toolkit.playbooks.cache import load_playbooks_index
from cortex_ps_toolkit.playbooks.copy import plan_playbooks_copy
from cortex_ps_toolkit.playbooks.delete import plan_playbooks_delete
from cortex_ps_toolkit.playbooks.service import refresh_playbooks_cache
from cortex_ps_toolkit.scripts import api as scripts_api
from cortex_ps_toolkit.scripts.cache import load_scripts_index
from cortex_ps_toolkit.scripts.copy import plan_scripts_copy
from cortex_ps_toolkit.scripts.delete import plan_scripts_delete
from cortex_ps_toolkit.scripts.service import refresh_scripts_cache
from cortex_ps_toolkit.integrations.delete import plan_integrations_delete
from cortex_ps_toolkit.xql.service import run_xql_query

from tests.conftest import LAB_TENANT_BY_SLUG, LAB_TENANT_SLUGS, LabTenant

pytestmark = pytest.mark.integration

_NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"
_XQL_QUERY = "dataset = xdr_data | limit 1"


def _platform(slug: str) -> Platform:
    return LAB_TENANT_BY_SLUG[slug]


def _operation_supported(operation_id: str, platform: Platform) -> bool:
    return get_operation(operation_id).is_available(platform)


def _assert_validate_ok(result: dict) -> None:
    """Require essential auth/connectivity checks; optional diagnostics may fail."""
    tenant_type = result["tenant_type"]
    passed = {check["id"] for check in result["checks"] if check["ok"]}
    if tenant_type == "xsoar6":
        assert "health" in passed, result
    else:
        assert {"healthcheck", "tenant_info"} <= passed, result


def _first_custom_script_id(slug: str) -> str | None:
    profile = get_profile(slug)
    index = load_scripts_index(profile)
    for item in index.get("scripts") or []:
        if not isinstance(item, dict):
            continue
        if item.get("system") is True:
            continue
        script_id = str(item.get("id") or "")
        if script_id:
            return script_id
    for item in index.get("scripts") or []:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


def _first_playbook_id(slug: str) -> str | None:
    profile = get_profile(slug)
    index = load_playbooks_index(profile)
    for item in index.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_validate_profile(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    result = validate_profile(slug)
    _assert_validate_ok(result)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_scripts_refresh_and_search(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("cache.scripts.refresh", _platform(slug)):
        pytest.skip(f"cache.scripts.refresh not supported on {_platform(slug).value}")
    refreshed = refresh_scripts_cache(slug)
    assert refreshed["count"] >= 0
    search = scripts_api.search_scripts(get_profile(slug))
    assert isinstance(search.scripts, list)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_scripts_load(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("cache.scripts.refresh", _platform(slug)):
        pytest.skip(f"cache.scripts.refresh not supported on {_platform(slug).value}")
    refresh_scripts_cache(slug)
    script_id = _first_custom_script_id(slug)
    if not script_id:
        pytest.skip(f"No scripts in cache for {slug}")
    loaded = scripts_api.get_script(get_profile(slug), script_id)
    assert str(loaded.get("name") or loaded.get("id") or "")


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_playbooks_refresh_search_and_get(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("cache.playbooks.refresh", _platform(slug)):
        pytest.skip(f"cache.playbooks.refresh not supported on {_platform(slug).value}")
    refresh_playbooks_cache(slug)
    profile = get_profile(slug)
    found = playbooks_api.search_playbooks(profile)
    assert isinstance(found, list)
    pb_id = _first_playbook_id(slug)
    if not pb_id:
        pytest.skip(f"No playbooks in cache for {slug}")
    playbook = playbooks_api.get_playbook(profile, pb_id)
    assert str(playbook.get("name") or playbook.get("id") or "")


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_lists_refresh(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("content.lists.manage", _platform(slug)):
        pytest.skip(f"content.lists.manage not supported on {_platform(slug).value}")
    result = refresh_lists_cache(slug)
    assert result["count"] >= 0


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_lists_delete_preview_not_found(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("content.lists.manage", _platform(slug)):
        pytest.skip(f"content.lists.manage not supported on {_platform(slug).value}")
    plan = plan_lists_delete(slug, [_NONEXISTENT_ID])
    assert plan["counts"]["not_found"] == 1


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_scripts_delete_preview_not_found(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("scripts.copy", _platform(slug)):
        pytest.skip(f"scripts.copy/delete not supported on {_platform(slug).value}")
    plan = plan_scripts_delete(slug, [_NONEXISTENT_ID])
    assert plan["counts"]["not_found"] == 1


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_integrations_delete_preview_not_found(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("integrations.delete", _platform(slug)):
        pytest.skip(f"integrations.delete not supported on {_platform(slug).value}")
    plan = plan_integrations_delete(slug, [_NONEXISTENT_ID])
    assert plan["counts"]["not_found"] == 1


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_playbooks_delete_preview_not_found(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("playbooks.copy", _platform(slug)):
        pytest.skip(f"playbooks.copy/delete not supported on {_platform(slug).value}")
    plan = plan_playbooks_delete(slug, [_NONEXISTENT_ID])
    assert plan["counts"]["not_found"] == 1


@pytest.mark.parametrize(
    "slug",
    [slug for slug in LAB_TENANT_SLUGS if _operation_supported("xql.run", LAB_TENANT_BY_SLUG[slug])],
)
def test_xql_run_limit_one(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    result = run_xql_query(slug, query=_XQL_QUERY, timeframe={"relativeTime": 3_600_000})
    assert result["query_id"]
    assert result["status"] in {"SUCCESS", "FAIL", "PENDING"}
    if result["status"] == "SUCCESS":
        assert result["row_count"] >= 0


def test_scripts_copy_preview_same_tenant(lab_tenant: LabTenant) -> None:
    if not _operation_supported("scripts.copy", lab_tenant.platform):
        pytest.skip(f"scripts.copy not supported on {lab_tenant.platform.value}")
    refresh_scripts_cache(lab_tenant.slug)
    script_id = _first_custom_script_id(lab_tenant.slug)
    if not script_id:
        pytest.skip("No scripts to plan copy")
    plan = plan_scripts_copy(
        lab_tenant.slug,
        lab_tenant.slug,
        [script_id],
        stop_on_conflict=True,
    )
    assert plan["counts"]["total"] == 1
    assert plan["items"][0]["script_id"] == script_id


def test_playbooks_copy_preview_same_tenant(lab_tenant: LabTenant) -> None:
    if not _operation_supported("playbooks.copy", lab_tenant.platform):
        pytest.skip(f"playbooks.copy not supported on {lab_tenant.platform.value}")
    refresh_playbooks_cache(lab_tenant.slug)
    pb_id = _first_playbook_id(lab_tenant.slug)
    if not pb_id:
        pytest.skip("No playbooks to plan copy")
    plan = plan_playbooks_copy(
        lab_tenant.slug,
        lab_tenant.slug,
        [pb_id],
        stop_on_conflict=True,
    )
    assert plan["counts"]["total"] == 1
    assert plan["items"][0]["playbook_id"] == pb_id
