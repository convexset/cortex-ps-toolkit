#!/usr/bin/env python3
"""Probe integration read/upload/delete APIs across lab tenant profiles.

Creates a temporary CptkUploadProbe integration, verifies integration/search,
then deletes it. Writes JSON summary when --output is set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cortex_ps_toolkit.credentials import get_profile, list_profiles
from cortex_ps_toolkit.integrations import api as integrations_api

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


def _delete_probe(profile_slug: str) -> dict[str, Any]:
    profile = get_profile(profile_slug)
    try:
        configuration = integrations_api.find_integration_configuration(profile, _PROBE_NAME)
    except KeyError:
        return {"status": "absent"}
    except Exception as exc:
        return {"status": "lookup_failed", "error": str(exc)}
    try:
        result = integrations_api.delete_integration_configuration(
            profile,
            _PROBE_NAME,
            configuration=configuration,
        )
        return {"status": "deleted", "status_code": result.status_code}
    except Exception as exc:
        return {"status": "delete_failed", "error": str(exc)}


def probe_profile(profile_slug: str) -> dict[str, Any]:
    profile = get_profile(profile_slug)
    row: dict[str, Any] = {
        "profile": profile_slug,
        "platform": profile.tenant_type.value,
    }

    try:
        commands = integrations_api.fetch_integration_commands(profile)
        row["read_commands"] = {
            "ok": True,
            "status_code": commands.status_code,
            "count": len(commands.data) if isinstance(commands.data, list) else 0,
        }
    except Exception as exc:
        row["read_commands"] = {"ok": False, "error": str(exc)}

    try:
        search = integrations_api.fetch_integration_search(profile)
        configurations = search.data.get("configurations") if isinstance(search.data, dict) else []
        row["read_search"] = {
            "ok": True,
            "status_code": search.status_code,
            "configuration_count": len(configurations) if isinstance(configurations, list) else 0,
        }
    except Exception as exc:
        row["read_search"] = {"ok": False, "error": str(exc)}

    cleanup = _delete_probe(profile_slug)
    row["preclean"] = cleanup

    try:
        upload = integrations_api.upload_integration_yaml(
            profile,
            _PROBE_YAML.encode("utf-8"),
            filename=f"{_PROBE_NAME}.yml",
        )
        row["copy_upload"] = {
            "ok": upload.status_code in {200, 201},
            "status_code": upload.status_code,
        }
    except Exception as exc:
        row["copy_upload"] = {"ok": False, "error": str(exc)}

    if row.get("copy_upload", {}).get("ok"):
        try:
            configuration = integrations_api.find_integration_configuration(profile, _PROBE_NAME)
            script = (configuration.get("integrationScript") or {}).get("script") or ""
            row["copy_verify"] = {
                "ok": configuration.get("name") == _PROBE_NAME and "register_module_line" in script,
            }
        except Exception as exc:
            row["copy_verify"] = {"ok": False, "error": str(exc)}

        row["delete"] = _delete_probe(profile_slug)
        row["delete"]["ok"] = row["delete"].get("status") == "deleted"
    else:
        row["delete"] = {"ok": False, "skipped": True}

    row["ok"] = all(
        row.get(key, {}).get("ok")
        for key in ("read_commands", "read_search", "copy_upload", "copy_verify", "delete")
        if isinstance(row.get(key), dict) and "skipped" not in row.get(key, {})
    )
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", help="Profile slug (default: all imported profiles)")
    parser.add_argument("--output", help="Write JSON results to this path")
    args = parser.parse_args(argv)

    slugs = args.profile or [profile.slug for profile in list_profiles()]
    results = [probe_profile(slug) for slug in slugs]
    payload = {"results": results}
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if all(row.get("ok") for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
