"""Live copy-fidelity probes: refresh → snapshot → renamed copy → refresh → diff.

Requires lab credentials (presets/credentials/lab-sources.json). Creates temporary
copies on the tenant and deletes them after each probe.
"""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.content.copy_probe import (
    assert_fidelity_equal,
    probe_list_copy_fidelity,
    probe_list_overwrite_fidelity,
    probe_playbook_copy_fidelity,
    probe_playbook_overwrite_fidelity,
    probe_script_copy_fidelity,
    probe_script_overwrite_fidelity,
)
from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.lists.cache import load_lists_index
from cortex_ps_toolkit.platforms import get_operation
from cortex_ps_toolkit.playbooks.cache import load_playbooks_index
from cortex_ps_toolkit.scripts.cache import load_scripts_index
from cortex_ps_toolkit.scripts.service import refresh_scripts_cache

from tests.conftest import LAB_TENANT_BY_SLUG, LAB_TENANT_SLUGS

pytestmark = pytest.mark.integration


def _operation_supported(operation_id: str, slug: str) -> bool:
    return get_operation(operation_id).is_available(LAB_TENANT_BY_SLUG[slug])


def _first_custom_script_id(slug: str) -> str | None:
    refresh_scripts_cache(slug)
    index = load_scripts_index(get_profile(slug))
    for item in index.get("scripts") or []:
        if isinstance(item, dict) and not item.get("system") and item.get("id"):
            return str(item["id"])
    for item in index.get("scripts") or []:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


def _first_playbook_id(slug: str) -> str | None:
    index = load_playbooks_index(get_profile(slug))
    for item in index.get("playbooks") or []:
        if isinstance(item, dict) and not item.get("system") and item.get("id"):
            return str(item["id"])
    for item in index.get("playbooks") or []:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


def _first_custom_list_id(slug: str) -> str | None:
    index = load_lists_index(get_profile(slug))
    for item in index.get("lists") or []:
        if isinstance(item, dict) and not item.get("system") and item.get("id"):
            return str(item["id"])
    for item in index.get("lists") or []:
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
    return None


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_script_copy_fidelity_same_tenant_rename(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("scripts.copy", slug):
        pytest.skip(f"scripts.copy not supported on {slug}")

    script_id = _first_custom_script_id(slug)
    if not script_id:
        pytest.skip(f"No scripts available on {slug}")

    result = probe_script_copy_fidelity(slug, script_id)
    if not result["diff"]["equal"]:
        pytest.fail(
            f"Script fidelity mismatch on {slug}: "
            f"{result['source_name']!r} → {result['copy_name']!r}; "
            f"diff={result['diff']['differences'][:8]}"
        )


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_playbook_copy_fidelity_same_tenant_rename(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("playbooks.copy", slug):
        pytest.skip(f"playbooks.copy not supported on {slug}")

    playbook_id = _first_playbook_id(slug)
    if not playbook_id:
        pytest.skip(f"No playbooks available on {slug}")

    result = probe_playbook_copy_fidelity(slug, playbook_id)
    assert_fidelity_equal(result)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_list_copy_fidelity_same_tenant_rename(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("content.lists.manage", slug):
        pytest.skip(f"content.lists.manage not supported on {slug}")

    list_id = _first_custom_list_id(slug)
    if not list_id:
        pytest.skip(f"No lists available on {slug}")

    result = probe_list_copy_fidelity(slug, list_id)
    assert_fidelity_equal(result)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_script_overwrite_fidelity(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("scripts.copy", slug):
        pytest.skip(f"scripts.copy not supported on {slug}")

    result = probe_script_overwrite_fidelity(slug)
    assert_fidelity_equal(result)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_playbook_overwrite_fidelity(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("playbooks.copy", slug):
        pytest.skip(f"playbooks.copy not supported on {slug}")

    result = probe_playbook_overwrite_fidelity(slug)
    assert_fidelity_equal(result)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_list_overwrite_fidelity(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    if not _operation_supported("content.lists.manage", slug):
        pytest.skip(f"content.lists.manage not supported on {slug}")

    result = probe_list_overwrite_fidelity(slug)
    assert_fidelity_equal(result)
