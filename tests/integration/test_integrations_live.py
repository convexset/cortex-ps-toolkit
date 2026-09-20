"""Live integration definition copy/delete preview and upload probes.

Requires lab credentials (presets/credentials/lab-sources.json).
Upload round-trip tests create a temporary custom integration and delete it afterward.
"""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.integrations import api as integrations_api
from cortex_ps_toolkit.integrations.copy import plan_integrations_copy
from cortex_ps_toolkit.integrations.metadata import is_copyable_integration
from cortex_ps_toolkit.integrations.service import refresh_integrations_cache
from cortex_ps_toolkit.platforms import get_operation

from tests.conftest import LAB_TENANT_BY_SLUG, LAB_TENANT_SLUGS, LabTenant

pytestmark = pytest.mark.integration

_PROBE_NAME = "CptkUploadProbe"
_PROBE_YAML = f"""category: Utilities
commonfields:
  id: {_PROBE_NAME}
  version: -1
configuration: []
description: Cortex PS Toolkit upload probe (auto-delete)
display: CPTK Upload Probe
name: {_PROBE_NAME}
script:
  commands: []
  dockerimage: demisto/python3:3.12.8.3295748
  runonce: false
  script: |
    register_module_line('{_PROBE_NAME}', 'start', __line__())
  subtype: python3
  type: python
fromversion: 6.0.0
"""


def _operation_supported(operation_id: str, slug: str) -> bool:
    return get_operation(operation_id).is_available(LAB_TENANT_BY_SLUG[slug])


def _first_copyable_integration_id(slug: str) -> str | None:
    refresh_integrations_cache(slug, include_packs=False, include_tenant_credentials=False)
    search = integrations_api.fetch_integration_search(get_profile(slug))
    configurations = search.data.get("configurations") if isinstance(search.data, dict) else []
    if not isinstance(configurations, list):
        return None
    for item in configurations:
        if not isinstance(item, dict):
            continue
        copyable, _reason = is_copyable_integration(item)
        if copyable:
            return str(item.get("id") or item.get("name") or "")
    return None


def _delete_probe_if_present(slug: str) -> None:
    profile = get_profile(slug)
    try:
        configuration = integrations_api.find_integration_configuration(profile, _PROBE_NAME)
    except KeyError:
        return
    integrations_api.delete_integration_configuration(profile, _PROBE_NAME, configuration=configuration)


def test_integrations_copy_preview_same_tenant(lab_tenant: LabTenant) -> None:
    if not _operation_supported("integrations.copy", lab_tenant.slug):
        pytest.skip(f"integrations.copy not supported on {lab_tenant.slug}")
    integration_id = _first_copyable_integration_id(lab_tenant.slug)
    if not integration_id:
        pytest.skip(f"No copyable custom integrations on {lab_tenant.slug}")
    plan = plan_integrations_copy(
        lab_tenant.slug,
        lab_tenant.slug,
        [integration_id],
        stop_on_conflict=True,
    )
    assert plan["counts"]["total"] == 1
    assert plan["items"][0]["integration_id"] == integration_id


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_integrations_read_apis(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")
    profile = get_profile(slug)
    commands = integrations_api.fetch_integration_commands(profile)
    assert commands.status_code == 200
    assert isinstance(commands.data, list)

    search = integrations_api.fetch_integration_search(profile)
    assert search.status_code == 200
    assert isinstance(search.data, dict)
    configurations = search.data.get("configurations")
    assert isinstance(configurations, list)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_integration_upload_round_trip(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")

    profile = get_profile(slug)
    _delete_probe_if_present(slug)
    try:
        upload = integrations_api.upload_integration_yaml(
            profile,
            _PROBE_YAML.encode("utf-8"),
            filename=f"{_PROBE_NAME}.yml",
        )
        assert upload.status_code in {200, 201}

        configuration = integrations_api.find_integration_configuration(profile, _PROBE_NAME)
        assert configuration.get("name") == _PROBE_NAME
        script = (configuration.get("integrationScript") or {}).get("script") or ""
        assert "register_module_line" in script
    finally:
        _delete_probe_if_present(slug)


@pytest.mark.parametrize("slug", LAB_TENANT_SLUGS)
def test_integration_delete_after_upload(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")

    profile = get_profile(slug)
    _delete_probe_if_present(slug)
    try:
        upload = integrations_api.upload_integration_yaml(
            profile,
            _PROBE_YAML.encode("utf-8"),
            filename=f"{_PROBE_NAME}.yml",
        )
        assert upload.status_code in {200, 201}
        configuration = integrations_api.find_integration_configuration(profile, _PROBE_NAME)
        delete = integrations_api.delete_integration_configuration(
            profile,
            _PROBE_NAME,
            configuration=configuration,
        )
        assert delete.status_code in {200, 204}
        with pytest.raises(KeyError):
            integrations_api.find_integration_configuration(profile, _PROBE_NAME)
    finally:
        _delete_probe_if_present(slug)
