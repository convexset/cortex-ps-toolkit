"""XSIAM content ZIP encoding for playbooks and scripts."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Mapping

import yaml

XSIAM_PACK_METADATA: dict[str, Any] = {
    "id": "",
    "version": 0,
    "cacheVersn": 0,
    "modified": "0001-01-01T00:00:00Z",
    "sizeInBytes": 0,
    "packID": "",
    "packName": "",
    "itemVersion": "",
    "fromServerVersion": "",
    "toServerVersion": "",
    "definitionId": "",
    "isOverridable": False,
    "vcShouldIgnore": False,
    "vcShouldKeepItemLegacyProdMachine": False,
    "commitMessage": "",
    "shouldCommit": False,
    "currentVersion": "",
    "name": "",
    "description": "",
    "updated": "0001-01-01T00:00:00Z",
    "created": "0001-01-01T00:00:00Z",
    "support": "",
    "author": "",
    "authorImage": "",
    "supportDetails": {"url": "", "email": ""},
    "beta": False,
    "deprecated": False,
    "certification": "",
    "serverMinVersion": "",
    "serverMaxVersion": "",
    "general": None,
    "tags": None,
    "rawTags": None,
}


def item_name_from_yaml(yaml_text: str, fallback: str) -> str:
    loaded = yaml.safe_load(yaml_text)
    if isinstance(loaded, dict):
        name = loaded.get("name") or loaded.get("id")
        if name:
            return str(name)
    return Path(fallback).stem


def xsiam_zip_member_path(content_kind: str, item_name: str) -> str:
    if content_kind == "script":
        return f"automation/automation-{item_name}.yml"
    if content_kind == "playbook":
        stem = item_name.replace(" ", "_").replace("/", "_")
        return f"playbook/playbook-{stem}.yml"
    raise ValueError(f"Unsupported XSIAM content kind: {content_kind!r}")


def xsiam_content_zip_bytes(
    yaml_text: str,
    *,
    content_kind: str,
    item_name: str | None = None,
    filename: str = "item.yml",
) -> bytes:
    resolved_name = item_name or item_name_from_yaml(yaml_text, filename)
    member = xsiam_zip_member_path(content_kind, resolved_name)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(XSIAM_PACK_METADATA))
        archive.writestr(member, yaml_text.encode("utf-8"))
    return buffer.getvalue()


def yaml_to_flat_zip_bytes(yaml_text: str, filename: str = "item.yml") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, yaml_text.encode("utf-8"))
    return buffer.getvalue()


def decode_zip_yaml_payload(data: bytes, *, content_kind: str) -> str:
    if not data:
        raise ValueError("Empty payload")
    raw = data
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            yaml_members = [name for name in archive.namelist() if name.lower().endswith((".yml", ".yaml"))]
            if content_kind == "script":
                preferred = [
                    name
                    for name in yaml_members
                    if "/automation-" in name.replace("\\", "/")
                ]
                if preferred:
                    yaml_members = preferred
            if not yaml_members:
                raise ValueError(f"ZIP contained no YAML: {archive.namelist()!r}")
            raw = archive.read(yaml_members[0])
    return raw.decode("utf-8")


def insert_failure_items(upload_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    objects = upload_response.get("objects")
    if not isinstance(objects, dict):
        return []
    if objects.get("succeeded_items"):
        return []
    failures = objects.get("failures_items") or []
    return [item for item in failures if isinstance(item, dict)]
