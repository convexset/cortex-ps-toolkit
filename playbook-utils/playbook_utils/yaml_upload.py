"""Upload playbook and script YAML exports to XSOAR 6, XSOAR 8, and XSIAM."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

import yaml

from .client import PlaybookClient, insert_failure_items, unwrap_saved_playbook
from .credentials import Platform
from .keys import JsonDict


@dataclass
class YamlUploadOutcome:
    path: str
    filename: str
    ok: bool
    entity_kind: str
    name: Optional[str] = None
    entity_id: Optional[str] = None
    already_exists: bool = False
    error: Optional[str] = None
    response: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "path": self.path,
            "filename": self.filename,
            "ok": self.ok,
            "entity_kind": self.entity_kind,
            "name": self.name,
            "entity_id": self.entity_id,
            "already_exists": self.already_exists,
            "error": self.error,
            "response": self.response,
        }


def collect_yaml_paths(paths: Sequence[str], *, recursive: bool = False) -> List[Path]:
    """Resolve file paths and/or directories to sorted ``.yml`` / ``.yaml`` files."""
    found: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if path.is_file():
            if path.suffix.lower() not in {".yml", ".yaml"}:
                raise ValueError(f"Not a YAML file: {path}")
            found.append(path.resolve())
            continue
        pattern = "**/*" if recursive else "*"
        for candidate in sorted(path.glob(pattern)):
            if candidate.is_file() and candidate.suffix.lower() in {".yml", ".yaml"}:
                found.append(candidate.resolve())
    deduped = sorted({item for item in found})
    if not deduped:
        raise FileNotFoundError("No .yml/.yaml files found in the given paths")
    return deduped


def read_yaml_upload(path: Path) -> tuple[str, str]:
    """Return ``(filename, yaml_text)`` for an on-disk export."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"YAML file is empty: {path}")
    return path.name, text


def _script_name_from_yaml(yaml_text: str, fallback: str) -> Optional[str]:
    try:
        loaded = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None
    if isinstance(loaded, dict):
        name = loaded.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        common = loaded.get("commonfields")
        if isinstance(common, dict):
            cid = common.get("id")
            if isinstance(cid, str) and cid.strip():
                return cid.strip()
    return fallback


def _playbook_name_from_yaml(yaml_text: str, fallback: str) -> Optional[str]:
    try:
        loaded = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None
    if isinstance(loaded, dict):
        name = loaded.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return fallback


def unwrap_saved_script(upload_response: Mapping[str, object]) -> Optional[JsonDict]:
    """Best-effort id/name extraction from script upload responses."""
    script = upload_response.get("script")
    if isinstance(script, dict):
        out: JsonDict = {}
        if script.get("id"):
            out["id"] = str(script["id"])
        if script.get("name"):
            out["name"] = str(script["name"])
        return out or None

    scripts = upload_response.get("scripts")
    if isinstance(scripts, list):
        for item in scripts:
            if isinstance(item, dict) and item.get("id"):
                out = {"id": str(item["id"])}
                if item.get("name"):
                    out["name"] = str(item["name"])
                return out

    selected = upload_response.get("selectedScript")
    if isinstance(selected, dict):
        for value in selected.values():
            if isinstance(value, dict) and value.get("id"):
                out = {"id": str(value["id"])}
                if value.get("name"):
                    out["name"] = str(value["name"])
                return out

    objects = upload_response.get("objects")
    if isinstance(objects, dict):
        items = objects.get("succeeded_items") or []
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
            out = {}
            if items[0].get("id"):
                out["id"] = str(items[0]["id"])
            if items[0].get("name"):
                out["name"] = str(items[0]["name"])
            return out or None
    return None


def _response_text(upload_response: Mapping[str, object]) -> str:
    parts: List[str] = []
    for key in ("error", "detail", "title"):
        value = upload_response.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    failures = insert_failure_items(upload_response)
    for item in failures:
        parts.append(str(item.get("error") or item))
    return "; ".join(parts)


def _failure_message(upload_response: Mapping[str, object]) -> Optional[str]:
    text = _response_text(upload_response)
    return text or None


def _already_exists(upload_response: Mapping[str, object]) -> bool:
    if int(upload_response.get("http_status") or 0) == 409:
        return True
    return "already exists" in _response_text(upload_response).lower()


def upload_playbook_file(client: PlaybookClient, path: Path) -> YamlUploadOutcome:
    filename, yaml_text = read_yaml_upload(path)
    response = client.save_yaml(yaml_text, filename=filename)
    saved = unwrap_saved_playbook(response) or {}
    failure = _failure_message(response)
    already_exists = _already_exists(response)
    ok = not failure or already_exists
    return YamlUploadOutcome(
        path=str(path),
        filename=filename,
        ok=ok,
        entity_kind="playbook",
        name=str(saved.get("name") or _playbook_name_from_yaml(yaml_text, path.stem) or ""),
        entity_id=str(saved.get("id") or "") or None,
        already_exists=already_exists,
        error=None if ok else failure,
        response=dict(response),
    )


def upload_script_file(client: PlaybookClient, path: Path) -> YamlUploadOutcome:
    filename, yaml_text = read_yaml_upload(path)
    response = client.save_script_yaml(yaml_text, filename=filename)
    saved = unwrap_saved_script(response) or {}
    failure = _failure_message(response)
    already_exists = _already_exists(response)
    script_name = str(saved.get("name") or _script_name_from_yaml(yaml_text, path.stem) or "")
    ok = not failure or already_exists
    if ok and client.credentials.platform.value == "xsiam" and script_name:
        if not client.xsiam_script_exists(script_name):
            ok = False
            failure = f"XSIAM scripts/insert returned success but script {script_name!r} is not retrievable"
    return YamlUploadOutcome(
        path=str(path),
        filename=filename,
        ok=ok,
        entity_kind="script",
        name=script_name,
        entity_id=str(saved.get("id") or "") or None,
        already_exists=already_exists,
        error=None if ok else failure,
        response=dict(response),
    )


def upload_many(
    client: PlaybookClient,
    paths: Iterable[Path],
    *,
    kind: str,
) -> List[YamlUploadOutcome]:
    upload_one = upload_playbook_file if kind == "playbook" else upload_script_file
    return [upload_one(client, path) for path in paths]


def format_upload_report(outcomes: Sequence[YamlUploadOutcome]) -> str:
    lines = [
        f"Uploaded: {sum(1 for item in outcomes if item.ok)}/{len(outcomes)}",
    ]
    for item in outcomes:
        status = "ok" if item.ok else "FAIL"
        suffix = " (already exists)" if item.already_exists else ""
        ident = item.name or item.filename
        if item.entity_id:
            ident = f"{ident} [{item.entity_id}]"
        lines.append(f"  [{status}] {item.filename} -> {ident}{suffix}")
        if item.error and not item.ok:
            lines.append(f"         {item.error}")
    return "\n".join(lines)
