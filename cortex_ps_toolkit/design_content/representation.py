"""Normalize and diff design-time content documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .bundle import STRIP_KEYS
from .types import AssetKind


@dataclass(frozen=True)
class DesignDiff:
    equal: bool
    diff_keys: tuple[str, ...]


def _drop_ignored(node: Any) -> Any:
    if isinstance(node, list):
        return [_drop_ignored(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        text = str(key)
        if text in STRIP_KEYS or text.lower() in {k.lower() for k in STRIP_KEYS}:
            continue
        out[text] = _drop_ignored(value)
    return out


def normalize_design_asset(document: Mapping[str, Any], asset: AssetKind) -> dict[str, Any]:
    normalized = _drop_ignored(dict(document))
    if asset in ("layouts", "classifiers"):
        normalized.pop("name", None)
        normalized.pop("id", None)
    if asset == "preprocess":
        normalized.pop("name", None)
        normalized.pop("id", None)
    if asset == "incident-fields":
        normalized.pop("id", None)
        normalized.pop("cliName", None)
    if asset == "incident-types":
        normalized.pop("id", None)
        normalized.pop("name", None)
    return normalized


def diff_design_assets(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    asset: AssetKind,
) -> DesignDiff:
    left = normalize_design_asset(expected, asset)
    right = normalize_design_asset(actual, asset)
    keys = sorted(set(left) | set(right))
    diff_keys = tuple(key for key in keys if left.get(key) != right.get(key))
    return DesignDiff(equal=not diff_keys, diff_keys=diff_keys)
