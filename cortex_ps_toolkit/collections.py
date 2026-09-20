"""Versioned JSON collection read/write."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional


def load_collection(path: Path, *, default: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    if not path.exists():
        if default is None:
            return {"version": 1}
        return dict(default)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Collection must be a JSON object: {path}")
    return payload


def save_collection(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def bump_collection(payload: MutableMapping[str, Any], *, version: int = 1) -> None:
    payload.setdefault("version", version)
