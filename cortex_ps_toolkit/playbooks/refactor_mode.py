"""Refactor execution mode: sequential (default) or parallel (experimental)."""

from __future__ import annotations

import os
from typing import Optional

from ..settings import load_settings

REFACTOR_MODE_SEQUENTIAL = "sequential"
REFACTOR_MODE_PARALLEL = "parallel"
_VALID_MODES = frozenset({REFACTOR_MODE_SEQUENTIAL, REFACTOR_MODE_PARALLEL})


def resolve_refactor_mode(override: Optional[str] = None) -> str:
    """Resolve effective refactor mode (override > env > settings > sequential)."""
    if override is not None:
        mode = str(override).strip().lower()
        if mode in _VALID_MODES:
            return mode
        raise ValueError(f"refactor_mode must be one of {sorted(_VALID_MODES)}; got {override!r}")

    env = os.environ.get("CORTEX_PS_REFACTOR_MODE", "").strip().lower()
    if env in _VALID_MODES:
        return env

    settings = load_settings()
    mode = str(settings.get("refactor_execution_mode") or REFACTOR_MODE_SEQUENTIAL).strip().lower()
    if mode in _VALID_MODES:
        return mode
    return REFACTOR_MODE_SEQUENTIAL


def is_parallel_mode(override: Optional[str] = None) -> bool:
    return resolve_refactor_mode(override) == REFACTOR_MODE_PARALLEL
