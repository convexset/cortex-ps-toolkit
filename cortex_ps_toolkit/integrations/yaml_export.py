"""Export integration ModuleConfiguration JSON to demisto-style YAML."""

from __future__ import annotations

from typing import Any, Mapping

from ..content.yaml_codec import dumps_yaml
from .metadata import integration_key


def _script_block(integration_script: Mapping[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {
        "commands": integration_script.get("commands") or [],
        "dockerimage": integration_script.get("dockerImage") or integration_script.get("dockerimage"),
        "runonce": bool(integration_script.get("runOnce", integration_script.get("runonce", False))),
        "script": integration_script.get("script") or "",
        "subtype": integration_script.get("subtype") or "python3",
        "type": integration_script.get("type") or "python",
        "feed": bool(integration_script.get("feed", False)),
    }
    optional_keys = (
        ("isFetch", "isFetch"),
        ("isFetchEvents", "isFetchEvents"),
        ("isFetchCredentials", "isFetchCredentials"),
        ("isFetchSamples", "isFetchSamples"),
        ("isMappable", "isMappable"),
        ("isRemoteSyncIn", "isRemoteSyncIn"),
        ("isRemoteSyncOut", "isRemoteSyncOut"),
        ("longRunning", "longRunning"),
        ("longRunningPortMapping", "longRunningPortMapping"),
        ("resetContext", "resetContext"),
    )
    for source_key, target_key in optional_keys:
        if source_key in integration_script:
            block[target_key] = integration_script[source_key]
    native_image = integration_script.get("nativeImage")
    if native_image:
        block["nativeImage"] = native_image
    return block


def configuration_to_yaml_document(configuration: Mapping[str, Any]) -> dict[str, Any]:
    name = integration_key(configuration)
    integration_script = configuration.get("integrationScript") or {}
    document: dict[str, Any] = {
        "category": configuration.get("category") or "Utilities",
        "commonfields": {"id": name, "version": -1},
        "configuration": configuration.get("configuration") or [],
        "description": configuration.get("description") or "",
        "display": configuration.get("display") or name,
        "name": name,
        "script": _script_block(integration_script if isinstance(integration_script, dict) else {}),
        "fromversion": configuration.get("fromServerVersion") or "6.0.0",
    }
    detailed = configuration.get("detailedDescription")
    if detailed:
        document["detailedDescription"] = detailed
    return document


def configuration_to_yaml_text(configuration: Mapping[str, Any]) -> str:
    return dumps_yaml(configuration_to_yaml_document(configuration))
