"""Build and import gzip tar content bundles for design-time assets."""

from __future__ import annotations

import copy
import gzip
import io
import json
import re
import tarfile
import uuid
from typing import Any, Mapping, Sequence

from ..core.paths import content_bundle_import_url
from ..core.client import TenantClient
from ..credentials import CredentialProfile
from ..platforms import Platform

STRIP_KEYS: frozenset[str] = frozenset({
    "version",
    "cacheVersn",
    "cacheversn",
    "modified",
    "created",
    "sequenceNumber",
    "sequencenumber",
    "primaryTerm",
    "primaryterm",
    "sortValues",
    "sortvalues",
    "highlight",
    "sizeInBytes",
    "sizeinbytes",
    "MainEngineInfo",
    "mainengineinfo",
    "definitionId",
    "definitionid",
    "commitMessage",
    "commitmessage",
    "shouldCommit",
    "shouldcommit",
    "vcShouldIgnore",
    "vcshouldignore",
    "vcShouldKeepItemLegacyProdMachine",
    "vcshouldkeepitemlegacyprodmachine",
    "propagationLabels",
    "propagationlabels",
    "packID",
    "packid",
    "packName",
    "packname",
    "itemVersion",
    "itemversion",
    "fromServerVersion",
    "fromserverversion",
    "toServerVersion",
    "toserverversion",
    "logicalVersion",
    "logicalversion",
    "prevName",
    "prevname",
    "nameRaw",
    "nameraw",
})


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())


def strip_server_fields(document: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(document))
    for key in list(out.keys()):
        if key in STRIP_KEYS or key.lower() in {k.lower() for k in STRIP_KEYS}:
            out.pop(key, None)
    return out


def derive_incident_field_cli_name(name: str) -> str:
    """Derive an incident-field cliName from a human-readable field name."""
    parts = re.findall(r"[A-Za-z0-9]+", name)
    if not parts:
        return "fieldCopy"
    first = parts[0].lower()
    tail = "".join(part[:1].upper() + part[1:] for part in parts[1:])
    return f"{first}{tail}"


def prepare_write_document(
    source: Mapping[str, Any],
    *,
    new_id: str,
    new_name: str | None = None,
    asset: str | None = None,
) -> dict[str, Any]:
    doc = strip_server_fields(source)
    doc["id"] = new_id
    if new_name is not None:
        doc["name"] = new_name
    if asset == "incident-fields":
        source_name = str(source.get("name") or source.get("id") or "")
        if new_name is not None and new_name != source_name:
            doc["cliName"] = derive_incident_field_cli_name(new_name)
    return doc


def bundle_member_name(asset: str, document: Mapping[str, Any]) -> str:
    name = str(document.get("name") or document.get("id") or "item")
    if asset == "layouts":
        return f"/layoutscontainer-{slug(name)}.json"
    if asset == "classifiers":
        return f"/classifier-{slug(name)}.json"
    if asset == "preprocess":
        item_id = str(document.get("id") or uuid.uuid4())
        return f"/preprocessrule-{item_id}-{slug(name)}.json"
    raise ValueError(f"Unknown asset for bundle member: {asset}")


def build_bundle_gzip(
    items: Sequence[tuple[str, Mapping[str, Any]]],
) -> bytes:
    """Build gzip-compressed tar from ``(asset_kind, document)`` pairs."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as archive:
        for asset, document in items:
            member_name = bundle_member_name(asset, document)
            payload = json.dumps(dict(document), indent=2).encode("utf-8")
            info = tarfile.TarInfo(name=member_name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return gzip.compress(buf.getvalue())


def import_bundle(profile: CredentialProfile, gzip_bytes: bytes) -> tuple[Any, int]:
    client = TenantClient(profile)
    url = content_bundle_import_url(profile.host.rstrip("/"), profile.tenant_type)
    filename = "design-content-bundle.tar.gz"
    return client.post_multipart_with_status(
        url,
        action="import content bundle",
        files={"file": (filename, gzip_bytes, "application/gzip")},
        timeout=300.0,
    )


def uses_direct_layout_import(platform: Platform) -> bool:
    return platform == Platform.XSOAR6


def uses_direct_classifier_import(platform: Platform) -> bool:
    return platform == Platform.XSOAR6


def uses_direct_preprocess_write(platform: Platform) -> bool:
    return platform == Platform.XSOAR6


def import_layout_direct(profile: CredentialProfile, document: Mapping[str, Any]) -> tuple[Any, int]:
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    payload = json.dumps(dict(document)).encode("utf-8")
    return client.post_multipart_with_status(
        f"{host}/layouts/import",
        action="import layout",
        files={"file": ("layout.json", payload, "application/json")},
    )


def import_classifier_direct(profile: CredentialProfile, document: Mapping[str, Any]) -> tuple[Any, int]:
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    payload = json.dumps(dict(document)).encode("utf-8")
    return client.post_multipart_with_status(
        f"{host}/classifier/import",
        action="import classifier",
        files={"file": ("classifier.json", payload, "application/json")},
    )


def write_preprocess_direct(profile: CredentialProfile, document: Mapping[str, Any]) -> tuple[Any, int]:
    client = TenantClient(profile)
    host = profile.host.rstrip("/")
    return client.post_json_with_status(
        f"{host}/preprocess/rule",
        action="write preprocess rule",
        payload=dict(document),
    )
