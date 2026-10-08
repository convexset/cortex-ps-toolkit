"""Prepare automation script JSON for tenant upload (copy vs overwrite)."""

from __future__ import annotations

import copy
from typing import Any, Mapping, MutableMapping

from ..portable_export_fields import DEFAULT_SCRIPT_EXCLUDE, load_portable_export_policy
from ..portable_export_remaps import DEFAULT_SCRIPT_KEY_RENAMES

# Back-compat alias; see ``portable_export_fields.DEFAULT_SCRIPT_EXCLUDE``.
SCRIPT_DROP_KEYS: frozenset[str] = DEFAULT_SCRIPT_EXCLUDE

# Back-compat alias; effective renames follow server config.
SCRIPT_YAML_KEY_RENAMES: dict[str, str] = dict(DEFAULT_SCRIPT_KEY_RENAMES)


def _drop_private_keys(node: MutableMapping[str, Any]) -> None:
    for key in list(node.keys()):
        if str(key).startswith("_"):
            del node[key]


def _drop_server_keys(node: MutableMapping[str, Any]) -> None:
    _drop_private_keys(node)
    drop = load_portable_export_policy().scripts.effective_exclude()
    for key in list(node.keys()):
        if key in drop or str(key).lower() in {k.lower() for k in drop}:
            del node[key]


def prepare_script_for_save(
    script: Mapping[str, Any],
    *,
    target_script_id: str | None = None,
    overwrite: bool = False,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Shape script JSON for tenant save (JSON on XSOAR 8, YAML elsewhere)."""
    doc = copy.deepcopy(dict(script))
    _drop_server_keys(doc)

    if target_name is not None:
        doc["name"] = target_name

    if overwrite:
        if not target_script_id:
            raise ValueError("target_script_id is required when overwrite=True")
        doc["id"] = target_script_id
    else:
        doc.pop("id", None)

    doc["version"] = -1
    return doc


def script_to_yaml_export(script: Mapping[str, Any]) -> dict[str, Any]:
    """Convert prepared script JSON to YAML-export key names (e.g. dockerimage)."""
    doc = copy.deepcopy(dict(script))
    renames = load_portable_export_policy().scripts.effective_key_renames()
    for src, dest in renames.items():
        if src in doc:
            doc[dest] = doc.pop(src)
        elif dest in doc and src not in doc:
            continue
    return doc


def script_to_xsiam_yaml_export(script: Mapping[str, Any]) -> dict[str, Any]:
    """Shape script JSON for XSIAM ``/scripts/insert`` (ZIP YAML).

    XSIAM expects tenant ids under ``commonfields.id``, not a top-level ``id``.
    """
    src = script_to_yaml_export(script)
    script_id = src.pop("id", None)
    src.pop("version", None)

    args = src.get("args") or src.get("arguments")
    docker = src.get("dockerimage") or src.get("dockerImage")
    runas = src.get("runas") or src.get("runAs") or "DBotWeakRole"
    runonce = src.get("runonce") if src.get("runonce") is not None else src.get("runOnce", False)
    scripttarget = (
        src.get("scripttarget")
        if src.get("scripttarget") is not None
        else src.get("scriptTarget", 0)
    )

    out: dict[str, Any] = {
        "name": str(src.get("name") or ""),
        "script": src.get("script") or "",
        "type": str(src.get("type") or "python"),
        "subtype": str(src.get("subtype") or "python3"),
        "tags": src.get("tags") or [],
        "enabled": bool(src.get("enabled", True)),
        "runas": str(runas),
        "runonce": bool(runonce),
        "scripttarget": scripttarget,
        "pswd": str(src.get("pswd") or ""),
        "engineinfo": src.get("engineinfo") or {},
        "mainengineinfo": src.get("mainengineinfo") or {},
        "signature": str(src.get("signature") or ""),
    }
    if script_id:
        out["commonfields"] = {"id": str(script_id), "version": -1}
    if args:
        out["args"] = args
    if docker:
        out["dockerimage"] = str(docker)
    comment = src.get("comment")
    if comment:
        out["comment"] = str(comment)
    return out
