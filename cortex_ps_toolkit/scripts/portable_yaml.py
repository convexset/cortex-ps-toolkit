"""Script YAML for manual import (XSOAR 6 UI / automation YAML save)."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from ..content.content_item_export import content_item_export_block, merge_export_document
from ..content.yaml_codec import dumps_yaml
from ..credentials import CredentialProfile
from ..portable_export_fields import load_portable_export_policy
from . import api
from .upload_prep import prepare_script_for_save, script_to_yaml_export


def script_to_portable_yaml_document(
    script: Mapping[str, Any],
    *,
    already_prepared: bool = False,
    pack_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Script YAML aligned with XSOAR 6 tenant / pack UI exports."""
    raw = pack_source if pack_source is not None else script
    prepared = script if already_prepared else prepare_script_for_save(script, overwrite=False)
    base = script_to_yaml_export(prepared)
    name = str(base.get("name") or "")
    runas = base.get("runas") or base.get("runAs") or "DBotWeakRole"
    runonce = base.get("runonce") if base.get("runonce") is not None else base.get("runOnce", False)
    scripttarget = (
        base.get("scripttarget")
        if base.get("scripttarget") is not None
        else base.get("scriptTarget", 0)
    )

    commonfields = {
        "id": name,
        "version": int(prepared.get("version", -1)) if prepared.get("version") is not None else -1,
    }
    core: dict[str, Any] = {
        "vcShouldKeepItemLegacyProdMachine": bool(
            raw.get("vcShouldKeepItemLegacyProdMachine", False),
        ),
        "name": name,
        "script": base.get("script") or "",
        "type": str(base.get("type") or "python"),
        "subtype": str(base.get("subtype") or "python3"),
        "tags": base.get("tags") or [],
        "enabled": bool(base.get("enabled", True)),
        "runas": str(runas),
        "runonce": bool(runonce),
        "scripttarget": scripttarget,
        "pswd": str(base.get("pswd") or ""),
        "engineinfo": base.get("engineinfo") or {},
        "mainengineinfo": base.get("mainengineinfo") or {},
    }
    optional_aliases: dict[str, tuple[str, ...]] = {
        "args": ("args", "arguments"),
        "dockerimage": ("dockerimage", "dockerImage"),
        "comment": ("comment",),
        "system": ("system",),
    }
    script_policy = load_portable_export_policy().scripts
    for field_name in script_policy.include_optional:
        aliases = optional_aliases.get(field_name, (field_name,))
        value = None
        for alias in aliases:
            if alias in base:
                value = base.get(alias)
                break
            if alias in raw:
                value = raw.get(alias)
                break
        if value is None:
            continue
        if field_name == "system" and value is not True:
            continue
        if field_name in ("args",):
            core[field_name] = value
        elif field_name == "dockerimage":
            core[field_name] = str(value)
        elif field_name == "comment":
            core[field_name] = str(value)
        else:
            core[field_name] = value

    return merge_export_document(
        {"commonfields": commonfields},
        content_item_export_block(raw),
        core,
    )


def build_portable_script_yaml(profile: CredentialProfile, script_id: str) -> str:
    """Build script YAML for bundle ZIP / offline XSOAR 6 import."""
    script = copy.deepcopy(api.get_script(profile, script_id))
    doc = script_to_portable_yaml_document(script, pack_source=script)
    return dumps_yaml(doc)
