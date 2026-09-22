"""On-disk automation script bodies (tenant YAML/JSON), separate from index metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from ..credentials import CredentialProfile
from .cache import find_script_in_index, scripts_cache_dir


def script_body_path(profile: CredentialProfile, script_id: str) -> Path:
    safe_id = str(script_id).replace("/", "_")
    return scripts_cache_dir(profile) / "bodies" / f"{safe_id}.json"


def load_script_body(profile: CredentialProfile, script_id: str) -> Optional[dict[str, Any]]:
    path = script_body_path(profile, script_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    script = payload.get("script")
    return dict(script) if isinstance(script, dict) else None


def save_script_body(profile: CredentialProfile, script_id: str, script: Mapping[str, Any]) -> Path:
    path = script_body_path(profile, script_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    index_meta = find_script_in_index(profile, script_id=script_id)
    payload = {
        "id": script_id,
        "modified": (index_meta or {}).get("modified"),
        "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": dict(script),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def count_script_bodies_on_disk(profile: CredentialProfile) -> int:
    bodies_dir = scripts_cache_dir(profile) / "bodies"
    if not bodies_dir.is_dir():
        return 0
    return sum(1 for path in bodies_dir.glob("*.json") if path.is_file())
