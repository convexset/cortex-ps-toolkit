"""Design-time content cache refresh and listing."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import load_body, load_index, write_cache
from .types import ASSET_KINDS, AssetKind


def refresh_asset_cache(profile: CredentialProfile | str, asset: AssetKind) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    items = api.fetch_asset_items(resolved, asset)
    path = write_cache(resolved, asset, items)
    return {
        "profile": resolved.slug,
        "asset": asset,
        "count": len(items),
        "cache_path": str(path),
        "refreshed_at": load_index(resolved, asset).get("refreshed_at"),
    }


def refresh_all_cache(profile: CredentialProfile | str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    results = {}
    for asset in ASSET_KINDS:
        results[asset] = refresh_asset_cache(resolved, asset)
    return {"profile": resolved.slug, "assets": results}


def list_cached_items(profile: CredentialProfile | str, asset: AssetKind) -> list[dict[str, Any]]:
    from .cache import list_cached

    resolved = get_profile(profile) if isinstance(profile, str) else profile
    return list_cached(resolved, asset)


def get_item_body(profile: CredentialProfile | str, asset: AssetKind, item_id: str) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = load_body(resolved, asset, item_id)
    if cached:
        return cached
    refresh_asset_cache(resolved, asset)
    cached = load_body(resolved, asset, item_id)
    if cached:
        return cached
    if asset == "layouts":
        return api.fetch_layout(resolved, item_id)
    items = api.fetch_asset_items(resolved, asset)
    for item in items:
        if str(item.get("id")) == str(item_id):
            return item
    raise KeyError(f"{asset} item not found: {item_id!r}")
