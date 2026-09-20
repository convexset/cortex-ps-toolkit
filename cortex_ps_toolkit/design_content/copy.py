"""Cross-tenant copy for design-time content assets."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Literal, Optional

from ..credentials import CredentialProfile, get_profile
from ..platforms import assert_operation_supported
from . import api
from .bundle import (
    build_bundle_gzip,
    derive_incident_field_cli_name,
    import_bundle,
    import_classifier_direct,
    import_layout_direct,
    prepare_write_document,
    uses_direct_classifier_import,
    uses_direct_layout_import,
    uses_direct_preprocess_write,
    write_preprocess_direct,
)
from .cache import list_cached, load_body
from .representation import diff_design_assets
from .copy_progress import notify_item_copied
from .service import get_item_body, refresh_asset_cache
from .types import OPERATION_BY_ASSET, AssetKind

CopyAction = Literal["copy", "update", "skip", "conflict", "blocked_pack"]


def _cached_target_ids(target: CredentialProfile, asset: AssetKind) -> set[str]:
    return {
        str(item.get("id"))
        for item in list_cached(target, asset)
        if item.get("id") is not None
    }


def _target_incident_field_cli_names(target: CredentialProfile) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in list_cached(target, "incident-fields"):
        field_id = item.get("id")
        if field_id is None:
            continue
        body = load_body(target, "incident-fields", str(field_id))
        cli_name = (body or item).get("cliName")
        if cli_name:
            mapping[str(cli_name)] = str(field_id)
    return mapping


def _resolve_target_identity(
    source: CredentialProfile,
    target: CredentialProfile,
    item_id: str,
    body: dict[str, Any],
    *,
    name_suffix: Optional[str] = None,
) -> tuple[str, str]:
    target_name = str(body.get("name") or item_id)
    if name_suffix:
        target_id = f"{target_name}{name_suffix}"
        target_name = target_id
    elif source.slug != target.slug:
        target_id = item_id
    else:
        target_id = f"{target_name}-copy"
        target_name = target_id
    return target_id, target_name


def _ensure_unique_incident_field_cli_name(
    cli_name: str,
    target_id: str,
    occupied: dict[str, str],
) -> str:
    if occupied.get(cli_name) in (None, target_id):
        return cli_name
    suffix = 2
    while True:
        candidate = f"{cli_name}Copy{suffix}" if suffix > 2 else f"{cli_name}Copy"
        if occupied.get(candidate) in (None, target_id):
            return candidate
        suffix += 1


def plan_asset_copy(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    asset: AssetKind,
    item_ids: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
) -> dict[str, Any]:
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile
    assert_operation_supported(OPERATION_BY_ASSET[asset], source.tenant_type)
    assert_operation_supported(OPERATION_BY_ASSET[asset], target.tenant_type)

    refresh_asset_cache(source, asset)
    refresh_asset_cache(target, asset)
    target_ids = _cached_target_ids(target, asset)
    target_field_cli_names = (
        _target_incident_field_cli_names(target)
        if asset == "incident-fields"
        else None
    )

    entries: list[dict[str, Any]] = []
    for item_id in item_ids:
        body = get_item_body(source, asset, item_id)
        if body.get("packID"):
            entries.append({
                "source_id": item_id,
                "action": "blocked_pack",
                "reason": "pack-owned asset",
            })
            continue
        target_id, target_name = _resolve_target_identity(
            source,
            target,
            item_id,
            body,
            name_suffix=name_suffix,
        )

        exists = target_id in target_ids
        if exists and stop_on_conflict:
            action: CopyAction = "conflict"
        elif exists and overwrite:
            action = "update"
        elif exists:
            action = "skip"
        else:
            action = "copy"

        write_method = "bundle"
        if asset == "layouts" and uses_direct_layout_import(target.tenant_type):
            write_method = "layout_import_or_bundle"
        elif asset == "classifiers" and uses_direct_classifier_import(target.tenant_type):
            write_method = "classifier_import_or_bundle"
        elif asset == "preprocess" and uses_direct_preprocess_write(target.tenant_type):
            write_method = "preprocess_direct_or_bundle"
        elif asset in ("incident-fields", "incident-types"):
            write_method = "direct_post"

        entries.append({
            "source_id": item_id,
            "target_id": target_id,
            "target_name": target_name,
            "action": action,
            "write_method": write_method,
        })

    return {
        "source_profile": source.slug,
        "target_profile": target.slug,
        "asset": asset,
        "entries": entries,
    }


def _write_items_bundle(
    target: CredentialProfile,
    asset: AssetKind,
    documents: list[dict[str, Any]],
) -> tuple[Any, int]:
    payload = build_bundle_gzip([(asset, doc) for doc in documents])
    return import_bundle(target, payload)


def copy_assets_to_tenant(
    source_profile: CredentialProfile | str,
    target_profile: CredentialProfile | str,
    asset: AssetKind,
    item_ids: list[str],
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    name_suffix: Optional[str] = None,
    prefer_direct_on_xsoar6: bool = True,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    plan = plan_asset_copy(
        source_profile,
        target_profile,
        asset,
        item_ids,
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        name_suffix=name_suffix,
    )
    source = get_profile(source_profile) if isinstance(source_profile, str) else source_profile
    target = get_profile(target_profile) if isinstance(target_profile, str) else target_profile

    if any(entry.get("action") == "conflict" for entry in plan["entries"]):
        plan["executed"] = False
        plan["error"] = "conflicts detected (stop_on_conflict)"
        return plan

    to_write: list[tuple[dict[str, Any], dict[str, Any]]] = []
    results: list[dict[str, Any]] = []
    target_field_cli_names = (
        _target_incident_field_cli_names(target)
        if asset == "incident-fields"
        else None
    )

    def _progress(event: dict[str, Any]) -> None:
        if on_progress:
            on_progress({"asset": asset, **event})

    for entry in plan["entries"]:
        action = entry.get("action")
        if action in ("skip", "blocked_pack"):
            results.append({**entry, "status": "skipped"})
            continue
        source_body = get_item_body(source, asset, str(entry["source_id"]))
        target_id = str(entry["target_id"])
        target_name = str(entry.get("target_name") or target_id)
        write_doc = prepare_write_document(
            source_body,
            new_id=target_id,
            new_name=target_name,
            asset=asset,
        )
        if asset == "incident-fields" and target_name != str(source_body.get("name") or entry["source_id"]):
            cli_name = derive_incident_field_cli_name(target_name)
            write_doc["cliName"] = _ensure_unique_incident_field_cli_name(
                cli_name,
                target_id,
                target_field_cli_names or {},
            )
        if asset == "preprocess" and action in ("copy", "update"):
            write_doc["id"] = str(uuid.uuid4()) if action == "copy" else write_doc.get("id", str(uuid.uuid4()))
        to_write.append((entry, write_doc))

    if not to_write:
        plan["results"] = results
        plan["executed"] = True
        return plan

    if asset in ("incident-fields", "incident-types"):
        for entry, write_doc in to_write:
            _progress({"phase": "step", "step": "write", "target_id": entry.get("target_id")})
            if asset == "incident-fields":
                _, status = api.write_incident_field(target, write_doc)
            else:
                _, status = api.write_incident_type(target, write_doc)
            result_entry = {**entry, "status": status, "channel": "direct"}
            results.append(result_entry)
            notify_item_copied(on_progress, asset, result_entry)
    else:
        use_direct = (
            prefer_direct_on_xsoar6
            and len(to_write) == 1
            and target.tenant_type.value == "xsoar6"
        )
        if use_direct:
            entry, write_doc = to_write[0]
            _progress({"phase": "step", "step": "write", "target_id": entry.get("target_id"), "channel": "direct"})
            if asset == "layouts":
                _, status = import_layout_direct(target, write_doc)
            elif asset == "classifiers":
                _, status = import_classifier_direct(target, write_doc)
            elif asset == "preprocess":
                _, status = write_preprocess_direct(target, write_doc)
            else:
                _, status = _write_items_bundle(target, asset, [write_doc])[1]
            result_entry = {**entry, "status": status, "channel": "direct"}
            results.append(result_entry)
            notify_item_copied(on_progress, asset, result_entry)
        else:
            _progress({"phase": "step", "step": "bundle_import", "count": len(to_write)})
            _, status = _write_items_bundle(target, asset, [doc for _, doc in to_write])
            for entry, _ in to_write:
                result_entry = {**entry, "status": status, "channel": "bundle"}
                results.append(result_entry)
                notify_item_copied(on_progress, asset, result_entry)

    refresh_asset_cache(target, asset)
    fidelity: list[dict[str, Any]] = []
    for entry, write_doc in to_write:
        target_id = str(entry["target_id"])
        try:
            read_back = get_item_body(target, asset, target_id)
            diff = diff_design_assets(write_doc, read_back, asset)
            fidelity.append({
                "target_id": target_id,
                "match": diff.equal,
                "diff_keys": list(diff.diff_keys),
            })
        except KeyError:
            fidelity.append({"target_id": target_id, "match": False, "diff_keys": ["not_found"]})

    plan["results"] = results
    plan["fidelity"] = fidelity
    plan["executed"] = True
    return plan
