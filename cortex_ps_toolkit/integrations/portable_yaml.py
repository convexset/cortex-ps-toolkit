"""Shape integration ModuleConfiguration JSON for XSOAR UI-style YAML export."""

from __future__ import annotations

from typing import Any, Mapping

from ..portable_export_fields import drop_keys_case_insensitive, load_portable_export_policy
from .metadata import integration_key


def _rename_keys(row: dict[str, Any], renames: Mapping[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        target = renames.get(key, key)
        out[target] = value
    return out


def _portable_config_param(
    row: Mapping[str, Any],
    *,
    policy: Any,
) -> dict[str, Any]:
    cleaned = dict(row)
    drop_keys_case_insensitive(cleaned, policy.exclude_config_param)
    if cleaned.get("options") is None:
        cleaned.pop("options", None)
    renamed = _rename_keys(cleaned, policy.effective_config_param_renames())
    return renamed


def _portable_command_argument(
    row: Mapping[str, Any],
    *,
    policy: Any,
) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return dict(row)  # type: ignore[arg-type]
    cleaned = dict(row)
    drop_keys_case_insensitive(cleaned, policy.exclude_command_argument)
    if not cleaned.get("required"):
        cleaned.pop("required", None)
    default = cleaned.get("default")
    if default in (None, False, ""):
        cleaned.pop("default", None)
    return cleaned


def _portable_command_output(
    row: Mapping[str, Any],
    *,
    policy: Any,
) -> dict[str, Any]:
    cleaned = dict(row)
    drop_keys_case_insensitive(cleaned, policy.exclude_command_output)
    if cleaned.get("contentPath") in (None, ""):
        cleaned.pop("contentPath", None)
    return cleaned


def _portable_command(
    row: Mapping[str, Any],
    *,
    policy: Any,
) -> dict[str, Any]:
    cleaned = dict(row)
    drop_keys_case_insensitive(cleaned, policy.exclude_command)
    arguments = [
        _portable_command_argument(item, policy=policy)
        for item in (cleaned.get("arguments") or [])
        if isinstance(item, Mapping)
    ]
    outputs = [
        _portable_command_output(item, policy=policy)
        for item in (cleaned.get("outputs") or [])
        if isinstance(item, Mapping)
    ]
    result: dict[str, Any] = {
        "name": cleaned.get("name"),
        "arguments": arguments,
    }
    if cleaned.get("description"):
        result["description"] = cleaned["description"]
    if outputs:
        result["outputs"] = outputs
    return result


def _portable_script_block(
    integration_script: Mapping[str, Any],
    *,
    policy: Any,
) -> dict[str, Any]:
    commands = [
        _portable_command(item, policy=policy)
        for item in (integration_script.get("commands") or [])
        if isinstance(item, Mapping)
    ]
    block: dict[str, Any] = {
        "commands": commands,
        "script": integration_script.get("script") or "",
        "type": integration_script.get("type") or "python",
        "subtype": integration_script.get("subtype") or "python3",
    }
    docker = integration_script.get("dockerImage") or integration_script.get("dockerimage")
    if docker:
        block["dockerimage"] = docker
    if "runOnce" in integration_script or "runonce" in integration_script:
        block["runonce"] = bool(
            integration_script.get("runOnce", integration_script.get("runonce", False)),
        )
    native = integration_script.get("nativeImage") or integration_script.get("nativeimage")
    if native:
        block["nativeimage"] = native
    for flag in policy.omit_script_flags_when_false:
        if flag not in integration_script:
            continue
        if integration_script.get(flag):
            block[flag] = integration_script[flag]
    port_mapping = integration_script.get("longRunningPortMapping")
    if port_mapping:
        block["longRunningPortMapping"] = port_mapping
    return block


def configuration_to_portable_yaml_document(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Build integration YAML document aligned with tenant UI export shape."""
    policy = load_portable_export_policy().integrations
    name = integration_key(configuration)
    integration_script = configuration.get("integrationScript") or {}
    if not isinstance(integration_script, Mapping):
        integration_script = {}

    config_rows = [
        _portable_config_param(item, policy=policy)
        for item in (configuration.get("configuration") or [])
        if isinstance(item, Mapping)
    ]

    detailed = configuration.get("detailedDescription") or configuration.get("detaileddescription")

    document: dict[str, Any] = {
        "commonfields": {"id": name, "version": -1},
        "vcShouldKeepItemLegacyProdMachine": bool(
            configuration.get("vcShouldKeepItemLegacyProdMachine", False),
        ),
        "name": name,
        "display": configuration.get("display") or name,
        "category": configuration.get("category") or "Utilities",
        "description": configuration.get("description") or "",
        "configuration": config_rows,
        "script": _portable_script_block(integration_script, policy=policy),
        "signature": configuration.get("signature") if configuration.get("signature") is not None else "",
        "restrictioncenter": (
            configuration.get("restrictionCenter")
            or configuration.get("restrictioncenter")
            or {}
        ),
    }
    image = configuration.get("image")
    if image:
        document["image"] = image
    if detailed:
        document["detaileddescription"] = detailed

    drop_keys_case_insensitive(document, policy.exclude_configuration)
    return document


def configuration_to_portable_yaml_document_ordered(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Same as ``configuration_to_portable_yaml_document`` with stable top-level key order."""
    policy = load_portable_export_policy().integrations
    base = configuration_to_portable_yaml_document(configuration)
    ordered: dict[str, Any] = {}
    for key in policy.include_top_level:
        if key in base:
            ordered[key] = base[key]
    for key, value in base.items():
        if key not in ordered:
            ordered[key] = value
    return ordered
