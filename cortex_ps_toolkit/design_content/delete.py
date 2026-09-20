"""Delete design-time content assets where platform supports it."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from . import api
from .service import refresh_asset_cache
from .types import AssetKind


def _delete_supported(profile: CredentialProfile, asset: AssetKind) -> bool:
    platform = profile.tenant_type.value
    if asset == "layouts":
        return platform in ("xsoar6", "xsoar8", "xsiam", "xdr5", "agentix")
    if asset in ("classifiers", "preprocess"):
        return platform in ("xsoar6", "xsoar8")
    if asset in ("incident-fields", "incident-types"):
        return True
    return False


def plan_asset_delete(
    profile: CredentialProfile | str,
    asset: AssetKind,
    item_ids: list[str],
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    supported = _delete_supported(resolved, asset)
    entries = [{"item_id": item_id, "deletable": supported} for item_id in item_ids]
    return {"profile": resolved.slug, "asset": asset, "entries": entries}


def delete_assets(
    profile: CredentialProfile | str,
    asset: AssetKind,
    item_ids: list[str],
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    results: list[dict[str, Any]] = []
    for item_id in item_ids:
        try:
            if asset == "layouts":
                body, status = api.delete_layout(resolved, item_id)
            elif asset == "classifiers":
                body, status = api.delete_classifier(resolved, item_id)
            elif asset == "preprocess":
                body, status = api.delete_preprocess_rule(resolved, item_id)
            elif asset == "incident-fields":
                body, status = api.delete_incident_field(resolved, item_id)
            elif asset == "incident-types":
                body, status = api.delete_incident_type(resolved, item_id)
            else:
                raise ValueError(f"Unknown asset: {asset}")
            results.append({"item_id": item_id, "status": status, "body": body})
        except api.UnsupportedDelete as exc:
            results.append({"item_id": item_id, "status": None, "error": str(exc)})
    refresh_asset_cache(resolved, asset)
    return {"profile": resolved.slug, "asset": asset, "results": results}
