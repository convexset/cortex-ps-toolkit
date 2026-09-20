"""Live integration: design-content copy on xsoar6 lab tenant."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.design_content.copy import copy_assets_to_tenant
from cortex_ps_toolkit.design_content.delete import delete_assets
from cortex_ps_toolkit.design_content.service import refresh_asset_cache

CRED_PATH = Path("/Users/weichen/Downloads/dev/bay/personal-xsoar6-credentials.json")


pytestmark = pytest.mark.skipif(not CRED_PATH.exists(), reason="xsoar6 lab credentials missing")


def _profile() -> CredentialProfile:
    raw = json.loads(CRED_PATH.read_text())
    slug = f"x6-design-{uuid.uuid4().hex[:8]}"
    return CredentialProfile.from_storage_dict({
        **raw,
        "tenant_type": "xsoar6",
        "label": slug,
        "slug": slug,
        "api_id": str(raw.get("id") or ""),
        "verify_ssl": bool(raw.get("verify_ssl", False)),
    })


def test_xsoar6_layout_classifier_copy_via_module() -> None:
    profile = _profile()
    refresh_asset_cache(profile, "layouts")
    refresh_asset_cache(profile, "classifiers")

    from cortex_ps_toolkit.design_content.cache import list_cached

    layouts = list_cached(profile, "layouts")
    classifiers = list_cached(profile, "classifiers")
    layout_id = next(item["id"] for item in layouts if not item.get("packID"))
    classifier_id = next(item["id"] for item in classifiers if not item.get("packID"))
    suffix = f"-cptk-{uuid.uuid4().hex[:6]}"

    layout_result = copy_assets_to_tenant(
        profile,
        profile,
        "layouts",
        [layout_id],
        name_suffix=suffix,
        prefer_direct_on_xsoar6=False,
    )
    assert layout_result["executed"] is True
    assert layout_result["fidelity"][0]["match"] is True

    classifier_result = copy_assets_to_tenant(
        profile,
        profile,
        "classifiers",
        [classifier_id],
        name_suffix=suffix,
        prefer_direct_on_xsoar6=False,
    )
    assert classifier_result["executed"] is True
    assert classifier_result["fidelity"][0]["match"] is True

    new_layout_id = layout_result["entries"][0]["target_id"]
    new_classifier_id = classifier_result["entries"][0]["target_id"]
    delete_assets(profile, "layouts", [new_layout_id])
    delete_assets(profile, "classifiers", [new_classifier_id])
