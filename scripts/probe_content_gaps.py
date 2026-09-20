#!/usr/bin/env python3
"""Probe remaining content API gaps documented in docs/api-compat/content-probe.md.

Writes JSON summary to /tmp/content-probe-gaps.json when run with lab credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cortex_ps_toolkit.core.client import TenantClient, TenantApiError
from cortex_ps_toolkit.core.paths import layout_delete_url
from cortex_ps_toolkit.credentials import get_profile
from cortex_ps_toolkit.platforms import Platform


def _probe_layout_delete(profile_slug: str) -> dict[str, Any]:
    profile = get_profile(profile_slug)
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    # Use a non-existent layout id — expect 404/400, not 405/500 routing failure.
    url = layout_delete_url(host, profile.tenant_type, "cptk-probe-nonexistent-layout")
    try:
        response = client.session.post(url, json={}, timeout=client.timeout)
        return {
            "profile": profile_slug,
            "platform": profile.tenant_type.value,
            "status_code": response.status_code,
            "routable": response.status_code not in (404, 405),
        }
    except TenantApiError as exc:
        return {
            "profile": profile_slug,
            "platform": profile.tenant_type.value,
            "error": str(exc),
            "status_code": exc.status_code,
            "routable": exc.status_code not in (404, 405) if exc.status_code else False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True, help="Profile slug(s) to probe")
    parser.add_argument("--output", default="/tmp/content-probe-gaps.json")
    args = parser.parse_args(argv)

    results = {"layout_delete": [_probe_layout_delete(slug) for slug in args.profile]}
    out = Path(args.output)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
