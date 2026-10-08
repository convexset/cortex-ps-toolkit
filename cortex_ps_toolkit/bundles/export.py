"""Build portable ZIP exports from bundle member lists."""

from __future__ import annotations

import copy
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Sequence

from ..content.yaml_codec import dumps_yaml
from ..credentials import CredentialProfile, get_profile
from ..design_content.bundle import slug, strip_server_fields
from ..design_content.bundle_presets import get_bundle_preset, resolve_bundle_items
from ..design_content.service import get_item_body
from ..lists.copy import normalize_list_data, resolve_list_entry
from ..platforms import assert_operation_supported
from ..playbooks import api as playbooks_api
from ..playbooks.portable_yaml import build_portable_playbook_yaml
from ..scripts import api as scripts_api
from ..integrations.bundle_helpers import assert_exportable_integration, get_configuration_for_bundle
from ..integrations.yaml_export import configuration_to_yaml_text
from ..scripts.portable_yaml import build_portable_script_yaml
from ..scripts.cache import find_script_in_index
from ..scripts.metadata import classify_script_entry


class BundleExportError(Exception):
    def __init__(self, message: str, *, missing: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.missing = missing or []


def field_kind(field_id: str) -> str:
    fid = str(field_id or "")
    if fid.startswith("generic_"):
        return "generic"
    if fid.startswith("evidence_"):
        return "evidence"
    if fid.startswith("incident_"):
        return "incident"
    return "other"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_export_items(
    source_profile: str,
    *,
    items: Sequence[dict[str, Any]] | None = None,
    bundle_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if items is not None and bundle_id:
        raise ValueError("Provide items or bundle_id, not both")
    meta: dict[str, Any] = {"source_profile": source_profile, "bundle_id": None, "bundle_name": None}
    if bundle_id:
        preset = get_bundle_preset(source_profile, bundle_id)
        meta["bundle_id"] = preset.get("id")
        meta["bundle_name"] = preset.get("name")
        raw_items = preset.get("items") or []
    elif items is not None:
        raw_items = list(items)
    else:
        raise ValueError("items or bundle_id required")

    resolved = resolve_bundle_items(source_profile, raw_items)
    if resolved.get("missing_count"):
        raise BundleExportError(
            f"{resolved['missing_count']} bundle member(s) missing on source tenant",
            missing=list(resolved.get("missing") or []),
        )
    return list(resolved.get("items") or []), meta


def plan_bundle_export(
    source_profile: str,
    *,
    items: Sequence[dict[str, Any]] | None = None,
    bundle_id: str | None = None,
) -> dict[str, Any]:
    resolved, meta = resolve_export_items(source_profile, items=items, bundle_id=bundle_id)
    buckets = _partition_resolved(resolved)
    return {
        "ok": True,
        "source_profile": source_profile,
        "exported_at": _now_iso(),
        "item_count": len(resolved),
        "bundle_id": meta.get("bundle_id"),
        "bundle_name": meta.get("bundle_name"),
        "sections": {key: len(val) for key, val in buckets.items() if val},
    }


def _partition_resolved(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "lists": [],
        "scripts": [],
        "playbooks": [],
        "integrations": [],
        "incident-types": [],
        "incident-fields": [],
        "layouts": [],
        "classifiers": [],
        "preprocess": [],
        "correlation-rules": [],
    }
    for row in items:
        asset = str(row.get("asset") or "").strip()
        if asset in buckets:
            buckets[asset].append(row)
    return buckets


def _allocate_name(used: set[str], base: str, ext: str) -> str:
    candidate = f"{base}{ext}"
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while True:
        candidate = f"{base}_{index}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _fetch_correlation_rule(profile: CredentialProfile, name: str) -> dict[str, Any]:
    from ..platform_admin import api as admin_api

    assert_operation_supported("content.correlation_rules.list", profile.tenant_type)
    rule = admin_api.get_correlation_rule(profile, name)
    if not rule:
        raise KeyError(f"Correlation rule not found: {name!r}")
    return strip_server_fields(rule)


def build_bundle_zip_bytes(
    source_profile: str,
    *,
    items: Sequence[dict[str, Any]] | None = None,
    bundle_id: str | None = None,
    bundle_name: str | None = None,
) -> tuple[bytes, str]:
    profile = get_profile(source_profile)
    resolved, meta = resolve_export_items(source_profile, items=items, bundle_id=bundle_id)
    buckets = _partition_resolved(resolved)
    display_name = bundle_name or meta.get("bundle_name") or "bundle-export"
    zip_filename = f"{slug(display_name) or 'bundle-export'}.zip"

    used_names: set[str] = set()
    incident_types: list[dict[str, Any]] = []
    incident_fields: list[dict[str, Any]] = []
    layouts: list[dict[str, Any]] = []
    classifiers: list[dict[str, Any]] = []
    correlation_rules: list[dict[str, Any]] = []
    preprocess_entries: list[tuple[str, dict[str, Any]]] = []
    list_entries: list[tuple[str, str, dict[str, Any]]] = []
    script_entries: list[tuple[str, str, dict[str, Any]]] = []
    playbook_entries: list[tuple[str, str, dict[str, Any]]] = []
    integration_entries: list[tuple[str, str, dict[str, Any]]] = []

    lists_manifest: list[dict[str, Any]] = []
    scripts_manifest: list[dict[str, Any]] = []
    playbooks_manifest: list[dict[str, Any]] = []
    integrations_manifest: list[dict[str, Any]] = []
    preprocess_manifest: list[dict[str, Any]] = []

    try:
        for row in buckets["incident-types"]:
            incident_types.append(
                strip_server_fields(get_item_body(profile, "incident-types", str(row["id"]))),
            )
        for row in buckets["incident-fields"]:
            body = strip_server_fields(get_item_body(profile, "incident-fields", str(row["id"])))
            incident_fields.append(body)
        for row in buckets["layouts"]:
            layouts.append(strip_server_fields(get_item_body(profile, "layouts", str(row["id"]))))
        for row in buckets["classifiers"]:
            classifiers.append(strip_server_fields(get_item_body(profile, "classifiers", str(row["id"]))))
        for row in buckets["preprocess"]:
            body = strip_server_fields(get_item_body(profile, "preprocess", str(row["id"])))
            rule_id = str(body.get("id") or row["id"])
            rule_name = str(body.get("name") or row.get("name") or rule_id)
            file_name = _allocate_name(used_names, f"preprocessrule-{rule_id}-{slug(rule_name)}", ".json")
            path = f"object-setup/preprocess/{file_name}"
            preprocess_entries.append((path, body))
            preprocess_manifest.append({"id": rule_id, "name": rule_name, "file": path})
        for row in buckets["correlation-rules"]:
            name = str(row.get("name") or row["id"])
            correlation_rules.append(_fetch_correlation_rule(profile, name))
        for row in buckets["integrations"]:
            integration_key = str(row["id"])
            configuration = get_configuration_for_bundle(profile, integration_key)
            try:
                assert_exportable_integration(configuration)
            except ValueError as exc:
                raise BundleExportError(str(exc)) from exc
            display = str(configuration.get("display") or configuration.get("name") or integration_key)
            file_name = _allocate_name(
                used_names,
                slug(integration_key) or "integration",
                ".yml",
            )
            path = f"integrations/{file_name}"
            yaml_text = configuration_to_yaml_text(configuration)
            integration_entries.append((path, yaml_text, configuration))
            integrations_manifest.append({
                "id": integration_key,
                "name": display,
                "file": path,
            })
        for row in buckets["lists"]:
            entry = resolve_list_entry(profile, str(row["id"]))
            list_name = str(entry.get("name") or row["id"])
            file_name = _allocate_name(used_names, slug(list_name) or "list", ".txt")
            path = f"lists/{file_name}"
            data = normalize_list_data(entry.get("data"), "")
            list_entries.append((path, data, entry))
            lists_manifest.append({
                "id": str(row["id"]),
                "name": list_name,
                "type": str(entry.get("type") or "plain_text"),
                "description": str(entry.get("description") or ""),
                "file": path,
            })
        for row in buckets["scripts"]:
            script_id = str(row["id"])
            meta_entry = find_script_in_index(profile, script_id=script_id) or {}
            script_name = str(meta_entry.get("name") or row.get("name") or script_id)
            file_name = _allocate_name(used_names, slug(script_name) or "script", ".yml")
            path = f"scripts/{file_name}"
            yaml_text = build_portable_script_yaml(profile, script_id)
            script_entries.append((path, yaml_text, meta_entry))
            scripts_manifest.append({
                "id": script_id,
                "name": script_name,
                "file": path,
                "origin": classify_script_entry({"id": script_id, **meta_entry}),
            })
        for row in buckets["playbooks"]:
            playbook_id = str(row["id"])
            yaml_text = build_portable_playbook_yaml(profile, playbook_id)
            pb_doc = playbooks_api.get_playbook(profile, playbook_id)
            pb_name = str(pb_doc.get("name") or row.get("name") or playbook_id)
            file_name = _allocate_name(used_names, slug(pb_name) or "playbook", ".yml")
            path = f"playbooks/{file_name}"
            playbook_entries.append((path, yaml_text, pb_doc))
            playbooks_manifest.append({
                "id": playbook_id,
                "name": pb_name,
                "file": path,
                "depth": "shallow",
            })
    except KeyError as exc:
        raise BundleExportError(f"Export failed: asset missing during fetch: {exc}") from exc

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def write_json(path: str, payload: Any) -> None:
            zf.writestr(path, json.dumps(payload, indent=2))

        if incident_types:
            write_json("object-setup/custom-incident-types.json", incident_types)
        if incident_fields:
            write_json("object-setup/custom-fields.json", {"incidentFields": incident_fields})
        if layouts:
            write_json("object-setup/custom-layouts.json", layouts)
        if classifiers:
            write_json("object-setup/classifiers-and-mappers.json", classifiers)
        if correlation_rules:
            write_json("object-setup/correlation-rules.json", correlation_rules)
        for path, body in preprocess_entries:
            write_json(path, body)
        if preprocess_manifest:
            write_json("object-setup/preprocess/manifest.json", {"items": preprocess_manifest})
        for path, data, _entry in list_entries:
            zf.writestr(path, data)
        if lists_manifest:
            write_json("lists/manifest.json", {"items": lists_manifest})
        for path, yaml_text, _conf in integration_entries:
            zf.writestr(path, yaml_text)
        if integrations_manifest:
            write_json("integrations/manifest.json", {"items": integrations_manifest})
        for path, yaml_text, _meta in script_entries:
            zf.writestr(path, yaml_text)
        if scripts_manifest:
            write_json("scripts/manifest.json", {"items": scripts_manifest})
        for path, yaml_text, _doc in playbook_entries:
            zf.writestr(path, yaml_text)
        if playbooks_manifest:
            write_json("playbooks/manifest.json", {"items": playbooks_manifest})

        object_setup_files = [
            path
            for path, present in (
                ("object-setup/custom-incident-types.json", bool(incident_types)),
                ("object-setup/custom-fields.json", bool(incident_fields)),
                ("object-setup/custom-layouts.json", bool(layouts)),
                ("object-setup/classifiers-and-mappers.json", bool(classifiers)),
                ("object-setup/correlation-rules.json", bool(correlation_rules)),
            )
            if present
        ]
        write_json(
            "bundle-manifest.json",
            {
                "bundle_id": meta.get("bundle_id"),
                "bundle_name": display_name,
                "source_profile": profile.slug,
                "exported_at": _now_iso(),
                "item_count": len(resolved),
                "object_setup_files": object_setup_files,
                "sections": {
                    "integrations": len(integrations_manifest),
                    "lists": len(lists_manifest),
                    "scripts": len(scripts_manifest),
                    "playbooks": len(playbooks_manifest),
                    "preprocess": len(preprocess_manifest),
                    "incident-types": len(incident_types),
                    "incident-fields": len(incident_fields),
                    "layouts": len(layouts),
                    "classifiers": len(classifiers),
                    "correlation-rules": len(correlation_rules),
                },
            },
        )

    return buf.getvalue(), zip_filename
