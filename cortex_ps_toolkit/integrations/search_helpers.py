"""Helpers for integration/search payloads."""

from __future__ import annotations

from typing import Any, Optional

from ..credentials import CredentialProfile
from . import api


def fetch_search_bundle(profile: CredentialProfile | str) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Return search payload, configuration lookup, and instances list."""
    result = api.fetch_integration_search(profile)
    data = result.data if isinstance(result.data, dict) else {}
    configurations = [item for item in (data.get("configurations") or []) if isinstance(item, dict)]
    instances = [item for item in (data.get("instances") or []) if isinstance(item, dict)]
    lookup: dict[str, dict[str, Any]] = {}
    for configuration in configurations:
        for key in (configuration.get("id"), configuration.get("name")):
            if key not in (None, ""):
                lookup[str(key)] = configuration
    return data, lookup, instances


def find_configuration(
    lookup: dict[str, dict[str, Any]],
    integration_id: str,
) -> Optional[dict[str, Any]]:
    return lookup.get(str(integration_id))


def instances_for_configuration(
    configuration: dict[str, Any],
    instances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    name = str(configuration.get("name") or "")
    brand = str(configuration.get("brand") or name)
    matches: list[dict[str, Any]] = []
    for instance in instances:
        instance_brand = str(instance.get("brand") or "")
        if instance_brand and instance_brand in {name, brand}:
            matches.append(instance)
    return matches
