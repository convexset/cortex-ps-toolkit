"""Portable integration YAML shaping (UI export alignment)."""

from __future__ import annotations

from pathlib import Path

import yaml

from cortex_ps_toolkit.integrations.portable_yaml import configuration_to_portable_yaml_document
from cortex_ps_toolkit.integrations.yaml_export import configuration_to_yaml_document

SAMPLES = Path("/Users/weichen/Downloads/dev/scratch/xsoar-samples")

INTEGRATION_FORBIDDEN_COMMAND = frozenset({
    "cartesian",
    "definitionid",
    "permitted",
    "polling",
    "execution",
})

INTEGRATION_FORBIDDEN_CONFIG_PARAM = frozenset({
    "defaultValue",
    "displaypassword",
    "displayPassword",
    "info",
})


def _load(name: str) -> dict:
    return yaml.safe_load((SAMPLES / name).read_text(encoding="utf-8"))


def _reference_to_api_configuration(reference: dict) -> dict:
    script = reference.get("script") or {}
    configuration_rows = []
    for row in reference.get("configuration") or []:
        api_row = dict(row)
        if "defaultvalue" in api_row:
            api_row["defaultValue"] = api_row.pop("defaultvalue")
        if "additionalinfo" in api_row:
            api_row["info"] = api_row.pop("additionalinfo")
        api_row.update(
            {
                "displayPassword": "",
                "hidden": False,
                "hiddenPassword": False,
                "options": None,
            },
        )
        configuration_rows.append(api_row)

    commands = []
    for command in script.get("commands") or []:
        noisy = dict(command)
        noisy.update(
            {
                "cartesian": False,
                "definitionId": "",
                "permitted": False,
                "polling": False,
                "execution": False,
            },
        )
        args = []
        for arg in noisy.get("arguments") or []:
            arg_noisy = dict(arg)
            arg_noisy.update(
                {
                    "default": False,
                    "deprecated": False,
                    "hidden": False,
                    "secret": False,
                    "type": "",
                    "required": False,
                },
            )
            args.append(arg_noisy)
        noisy["arguments"] = args
        commands.append(noisy)

    return {
        "name": reference["name"],
        "display": reference["display"],
        "category": reference["category"],
        "description": reference.get("description"),
        "detailedDescription": reference.get("detaileddescription"),
        "image": reference.get("image"),
        "vcShouldKeepItemLegacyProdMachine": reference.get("vcShouldKeepItemLegacyProdMachine"),
        "signature": reference.get("signature"),
        "restrictionCenter": reference.get("restrictioncenter"),
        "configuration": configuration_rows,
        "integrationScript": {
            "commands": commands,
            "script": script.get("script"),
            "type": script.get("type"),
            "subtype": script.get("subtype"),
            "dockerImage": script.get("dockerimage"),
            "runOnce": script.get("runonce"),
            "nativeImage": script.get("nativeimage"),
            "feed": False,
            "isFetch": False,
        },
    }


def test_portable_integration_strips_command_and_config_noise() -> None:
    reference = _load("ProtectedHTTPCall.yml")
    api_row = _reference_to_api_configuration(reference)
    portable = configuration_to_portable_yaml_document(api_row)

    top_lower = {str(k).lower() for k in portable}
    assert "fromversion" not in top_lower
    assert "detailedDescription" not in portable
    assert portable.get("detaileddescription")

    first_param = portable["configuration"][0]
    param_keys_lower = {str(k).lower() for k in first_param}
    assert "defaultvalue" in param_keys_lower
    assert not param_keys_lower & INTEGRATION_FORBIDDEN_CONFIG_PARAM

    help_cmd = portable["script"]["commands"][0]
    cmd_keys_lower = {str(k).lower() for k in help_cmd}
    assert not cmd_keys_lower & INTEGRATION_FORBIDDEN_COMMAND

    path_arg = portable["script"]["commands"][1]["arguments"][0]
    assert set(path_arg.keys()) <= {"name", "description"}


def test_portable_integration_includes_signature_and_vc_flags() -> None:
    reference = _load("ProtectedHTTPCall.yml")
    api_row = _reference_to_api_configuration(reference)
    portable = configuration_to_yaml_document(api_row)
    assert portable["signature"] == ""
    assert portable["restrictioncenter"] == {}
    assert portable["vcShouldKeepItemLegacyProdMachine"] is False
    assert portable["script"].get("nativeimage") == reference["script"].get("nativeimage")
    assert "feed" not in portable["script"]
    assert "isFetch" not in portable["script"]
