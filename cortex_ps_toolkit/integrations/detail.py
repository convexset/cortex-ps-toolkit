"""Integration definition and instance detail payloads for the web viewer."""

from __future__ import annotations

from typing import Any

from ..credentials import CredentialProfile, get_profile
from . import api
from .cache import load_scope_cache
from .sanitize import sanitize_configuration_row, sanitize_instance_row, sanitize_search_payload


def _index_bodies(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bodies: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        item_name = str(item.get("name") or "")
        if item_id:
            bodies[item_id] = item
        if item_name and item_name not in bodies:
            bodies[item_name] = item
    return bodies


def index_configuration_bodies(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _index_bodies(items)


def index_instance_bodies(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _index_bodies(items)


def index_command_bodies(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _index_bodies(items)


def split_integration_definition(document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    doc = dict(document)
    integration_script = dict(doc.get("integrationScript") or {})
    script_text = str(integration_script.pop("script", "") or "")
    doc["integrationScript"] = integration_script
    return doc, script_text


def split_instance_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = dict(document)
    parameters = doc.pop("data", None)
    if parameters is None:
        return doc, []
    if isinstance(parameters, list):
        return doc, [item for item in parameters if isinstance(item, dict)]
    if isinstance(parameters, dict):
        return doc, [parameters]
    return doc, []


def split_commands_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = dict(document)
    commands = doc.pop("commands", None)
    if commands is None:
        return doc, []
    if isinstance(commands, list):
        return doc, [item for item in commands if isinstance(item, dict)]
    if isinstance(commands, dict):
        return doc, [commands]
    return doc, []


def _lookup_body(
    bodies: dict[str, dict[str, Any]],
    item_id: str,
) -> dict[str, Any] | None:
    needle = str(item_id)
    if needle in bodies:
        return dict(bodies[needle])
    for item in bodies.values():
        if str(item.get("id") or "") == needle or str(item.get("name") or "") == needle:
            return dict(item)
    return None


def _configuration_bodies(profile: CredentialProfile | str) -> dict[str, dict[str, Any]]:
    data = load_scope_cache(profile, "instances")
    bodies = data.get("configuration_bodies")
    if isinstance(bodies, dict):
        return {
            str(key): dict(value)
            for key, value in bodies.items()
            if isinstance(value, dict)
        }
    return {}


def _instance_bodies(profile: CredentialProfile | str) -> dict[str, dict[str, Any]]:
    data = load_scope_cache(profile, "instances")
    bodies = data.get("instance_bodies")
    if isinstance(bodies, dict):
        return {
            str(key): dict(value)
            for key, value in bodies.items()
            if isinstance(value, dict)
        }
    return {}


def _command_bodies(profile: CredentialProfile | str) -> dict[str, dict[str, Any]]:
    data = load_scope_cache(profile, "commands")
    bodies = data.get("integration_bodies")
    if isinstance(bodies, dict):
        return {
            str(key): dict(value)
            for key, value in bodies.items()
            if isinstance(value, dict)
        }
    return {}


def get_integration_definition_detail(
    profile: CredentialProfile | str,
    integration_id: str,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = _lookup_body(_configuration_bodies(resolved), integration_id)
    if cached is None:
        document = api.find_integration_configuration(resolved, integration_id)
        cached = sanitize_configuration_row(document)
    configuration, script_text = split_integration_definition(cached)
    integration_script = configuration.get("integrationScript") or {}
    script_language = str(integration_script.get("type") or integration_script.get("language") or "")
    return {
        "profile": resolved.slug,
        "id": str(configuration.get("id") or integration_id),
        "name": str(configuration.get("name") or ""),
        "kind": "integration_definition",
        "configuration": configuration,
        "script": script_text,
        "script_language": script_language,
    }


def get_integration_instance_detail(
    profile: CredentialProfile | str,
    instance_id: str,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = _lookup_body(_instance_bodies(resolved), instance_id)
    if cached is None:
        result = api.fetch_integration_search(resolved)
        sanitized = sanitize_search_payload(result.data)
        for item in sanitized.get("instances") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") == str(instance_id) or str(item.get("name") or "") == str(instance_id):
                cached = item
                break
        if cached is None:
            raise KeyError(f"integration instance not found: {instance_id}")
    configuration, parameters = split_instance_document(sanitize_instance_row(cached))
    return {
        "profile": resolved.slug,
        "id": str(configuration.get("id") or instance_id),
        "name": str(configuration.get("name") or ""),
        "kind": "integration_instance",
        "configuration": configuration,
        "parameters": parameters,
    }


def get_integration_commands_detail(
    profile: CredentialProfile | str,
    integration_id: str,
) -> dict[str, Any]:
    resolved = get_profile(profile) if isinstance(profile, str) else profile
    cached = _lookup_body(_command_bodies(resolved), integration_id)
    if cached is None:
        result = api.fetch_integration_commands(resolved)
        needle = str(integration_id)
        for item in result.data:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") == needle or str(item.get("name") or "") == needle:
                cached = dict(item)
                break
        if cached is None:
            raise KeyError(f"integration commands not found: {integration_id}")
    configuration, commands = split_commands_document(cached)
    return {
        "profile": resolved.slug,
        "id": str(configuration.get("id") or integration_id),
        "name": str(configuration.get("name") or ""),
        "kind": "integration_commands",
        "configuration": configuration,
        "commands": commands,
    }
