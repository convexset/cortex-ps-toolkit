"""Load refactor preset configs shipped under presets/refactor/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..paths import package_root

_PRESETS_DIR = package_root() / "presets" / "refactor"


def list_refactor_presets() -> list[dict[str, Any]]:
    if not _PRESETS_DIR.is_dir():
        return []
    presets: list[dict[str, Any]] = []
    for path in sorted(_PRESETS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("id", path.stem)
            presets.append(payload)
    return presets


def get_refactor_preset(preset_id: str) -> dict[str, Any]:
    path = _PRESETS_DIR / f"{preset_id}.json"
    if not path.is_file():
        path = _PRESETS_DIR / preset_id
        if path.suffix != ".json":
            path = path.with_suffix(".json")
    if not path.is_file():
        raise KeyError(f"Refactor preset not found: {preset_id!r}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Preset must be a JSON object: {path}")
    payload.setdefault("id", path.stem)
    return payload


def resolve_workflow_preset(preset: dict[str, Any]) -> dict[str, Any]:
    """Expand workflow presets that reference step preset ids."""
    steps = preset.get("steps")
    if not steps:
        return preset
    resolved_steps: list[dict[str, Any]] = []
    for step in steps:
        if isinstance(step, str):
            resolved_steps.append(get_refactor_preset(step))
        elif isinstance(step, dict):
            resolved_steps.append(step)
    expanded = dict(preset)
    expanded["resolved_steps"] = resolved_steps
    return expanded
