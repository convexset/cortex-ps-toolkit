"""Live script delete round-trip on lab tenants."""

from __future__ import annotations

import pytest

from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.scripts import api as scripts_api
from cortex_ps_toolkit.scripts.service import refresh_scripts_cache

from tests.conftest import LAB_TENANT_SLUGS

pytestmark = pytest.mark.integration

_PROBE_NAME = "CptkScriptDeleteProbe"
_PROBE_YAML = f"""commonfields:
  id: {_PROBE_NAME}
  version: -1
name: {_PROBE_NAME}
script: |
  register_module_line('{_PROBE_NAME}', 'start', __line__())
type: python
subtype: python3
tags: []
dockerimage: demisto/python3:3.12.8.3295748
fromversion: 6.0.0
"""


def _delete_probe_if_present(slug: str) -> None:
    profile = get_profile(slug)
    try:
        found = scripts_api.get_script_by_name(profile, _PROBE_NAME)
    except KeyError:
        return
    script_id = str(found.get("id") or "")
    if script_id:
        scripts_api.delete_script(profile, script_id=script_id)


@pytest.mark.parametrize("slug", ("personal-xsoar6", "xsoar-japac-dev"))
def test_script_delete_round_trip(slug: str, available_lab_slugs: set[str]) -> None:
    if slug not in available_lab_slugs:
        pytest.skip(f"Profile {slug!r} not configured")

    profile = get_profile(slug)
    _delete_probe_if_present(slug)
    try:
        upload_status = scripts_api.save_script_yaml(
            profile,
            _PROBE_YAML,
            filename=f"{_PROBE_NAME}.yml",
        )[1]
        assert upload_status == 200
        refresh_scripts_cache(slug)
        found = scripts_api.get_script_by_name(profile, _PROBE_NAME)
        script_id = str(found.get("id") or "")
        assert script_id

        _response, delete_status = scripts_api.delete_script(profile, script_id=script_id)
        assert delete_status == 200

        refresh_scripts_cache(slug)
        with pytest.raises(KeyError):
            scripts_api.get_script_by_name(profile, _PROBE_NAME)
    finally:
        _delete_probe_if_present(slug)
