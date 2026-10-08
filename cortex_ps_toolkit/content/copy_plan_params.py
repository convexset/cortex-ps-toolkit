"""Shared keyword arguments for copy plan and execute functions."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .copy_modes import CopyMode, parse_copy_mode


def normalize_copy_kwargs(
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    mode = parse_copy_mode(
        overwrite=overwrite,
        stop_on_conflict=stop_on_conflict,
        copy_mode=copy_mode,
    )
    if mode == "copy_as_new" and stop_on_conflict:
        raise ValueError("stop_on_conflict cannot be used with copy_as_new")
    suffix = str(rename_suffix or "")
    if mode == "copy_as_new" and not suffix and not rename_map:
        suffix = "_copy"
    rmap = {str(k): str(v) for k, v in (rename_map or {}).items()}
    return {
        "copy_mode": mode,
        "overwrite": mode == "overwrite",
        "stop_on_conflict": stop_on_conflict,
        "rename_suffix": suffix,
        "rename_map": rmap,
    }


def copy_kwargs_from_body(body: Mapping[str, Any]) -> dict[str, Any]:
    rename_map_raw = body.get("rename_map") or {}
    rename_map = (
        {str(k): str(v) for k, v in rename_map_raw.items()}
        if isinstance(rename_map_raw, dict)
        else {}
    )
    return {
        "overwrite": bool(body.get("overwrite")),
        "stop_on_conflict": bool(body.get("stop_on_conflict")),
        "copy_mode": body.get("copy_mode"),
        "rename_suffix": str(body.get("rename_suffix") or ""),
        "rename_map": rename_map,
    }


def integration_copy_plan_kwargs(opts: Mapping[str, Any]) -> dict[str, Any]:
    """Copy plan kwargs for integrations (no rename / copy_as_new)."""
    return {
        "overwrite": bool(opts.get("overwrite")),
        "stop_on_conflict": bool(opts.get("stop_on_conflict")),
    }


def effective_upload_name(item: Mapping[str, Any], *, fallback: str) -> str:
    action = str(item.get("action") or "")
    if action == "copy_as_new":
        return str(item.get("proposed_name") or fallback)
    return fallback
