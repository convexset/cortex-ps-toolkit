"""Copy mode parsing and name resolution for cross-tenant copy plans."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

CopyMode = Literal["skip", "overwrite", "copy_as_new"]

CopyAction = Literal["copy", "update", "skip", "conflict", "copy_as_new"]


def parse_copy_mode(
    *,
    overwrite: bool = False,
    stop_on_conflict: bool = False,
    copy_mode: Optional[str] = None,
) -> CopyMode:
    """Resolve API flags into a single copy mode (stop_on_conflict stays a separate plan flag)."""
    if copy_mode:
        mode = str(copy_mode).strip().lower().replace("-", "_")
        if mode in ("skip", "overwrite", "copy_as_new", "copyasnew", "rename"):
            if mode in ("copyasnew", "rename"):
                return "copy_as_new"
            return mode  # type: ignore[return-value]
        raise ValueError(f"Unknown copy_mode: {copy_mode!r}")
    if stop_on_conflict and overwrite:
        raise ValueError("overwrite and stop_on_conflict cannot both be enabled")
    if overwrite:
        return "overwrite"
    return "skip"


def proposed_name(
    source_name: str,
    *,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    item_key: str = "",
) -> str:
    if rename_map and item_key and item_key in rename_map:
        return str(rename_map[item_key]).strip() or source_name
    suffix = rename_suffix or ""
    return f"{source_name}{suffix}"


def classify_copy_action(
    *,
    existing: Optional[dict[str, Any]],
    mode: CopyMode,
    source_name: str,
    rename_suffix: str = "",
    rename_map: Optional[Mapping[str, str]] = None,
    item_key: str = "",
    name_exists: Optional[Any] = None,
    stop_on_conflict: bool = False,
) -> tuple[CopyAction, dict[str, Any]]:
    """Classify one item; extra keys on item (proposed_name, collision_reason)."""
    extra: dict[str, Any] = {}
    if not existing:
        return "copy", extra

    if mode == "overwrite":
        return "update", extra

    if mode == "copy_as_new":
        new_name = proposed_name(
            source_name,
            rename_suffix=rename_suffix,
            rename_map=rename_map,
            item_key=item_key,
        )
        extra["proposed_name"] = new_name
        if new_name == source_name:
            extra["collision_reason"] = "proposed_name_same_as_source"
        checker = name_exists
        if checker is not None:
            collision = checker(new_name)
            if collision:
                extra["proposed_name_collision"] = True
                return "conflict", extra
        return "copy_as_new", extra

    if stop_on_conflict:
        return "conflict", extra
    return "skip", extra


def plan_would_abort(
    *,
    mode: CopyMode,
    stop_on_conflict: bool,
    conflicts: list[dict[str, Any]],
) -> bool:
    if mode == "copy_as_new":
        return bool(conflicts)
    return stop_on_conflict and bool(conflicts)
