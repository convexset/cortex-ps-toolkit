"""Strip secrets from integration instance payloads before caching."""

from __future__ import annotations

from typing import Any


_SECRET_KEYS = frozenset({
    "password",
    "configvalues",
    "pyramidAPIEncryptedAuthenticationHeader",
    "pyramidAPIEncryptedAuthenticationHeaderTenants",
})


def _strip_mapping(value: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if key in _SECRET_KEYS:
            continue
        if key == "data" and isinstance(item, list):
            cleaned[key] = [
                {
                    k: v
                    for k, v in row.items()
                    if k not in {"value", "hasvalue", "displayPassword"}
                }
                if isinstance(row, dict)
                else row
                for row in item
            ]
            continue
        cleaned[key] = item
    return cleaned


def sanitize_instance_row(row: dict[str, Any]) -> dict[str, Any]:
    return _strip_mapping(dict(row))


def sanitize_configuration_row(row: dict[str, Any]) -> dict[str, Any]:
    return _strip_mapping(dict(row))


def sanitize_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    instances = [
        sanitize_instance_row(item)
        for item in (payload.get("instances") or [])
        if isinstance(item, dict)
    ]
    configurations = [
        sanitize_configuration_row(item)
        for item in (payload.get("configurations") or [])
        if isinstance(item, dict)
    ]
    result["instances"] = instances
    result["configurations"] = configurations
    if "health" in result:
        result["health"] = {"redacted": True, "keys": sorted(result["health"].keys())}
    if "engines" in result and isinstance(result["engines"], dict):
        engines = dict(result["engines"])
        if isinstance(engines.get("engines"), list):
            engines["engines"] = [
                _strip_mapping(item) if isinstance(item, dict) else item
                for item in engines["engines"]
            ]
        result["engines"] = engines
    return result
