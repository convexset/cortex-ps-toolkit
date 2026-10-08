"""Validate visual specs against result rows (no aggregation in viz layer)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..schema import infer_column_type, infer_schema
from .registry import get_chart_type, map_column_type_to_field_type
from .spec import VisualSpec


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "schema": self.schema,
        }


def _column_set(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(str(k) for k in row.keys())
    return keys


def _field_type_ok(rows: Sequence[Mapping[str, Any]], field_name: str, accepted: frozenset[str]) -> bool:
    inferred = infer_column_type(rows, field_name)
    mapped = map_column_type_to_field_type(inferred)
    if mapped in accepted:
        return True
    if mapped == "text" and "text" in accepted:
        return True
    return False


def validate_visual_spec(rows: Sequence[Mapping[str, Any]], spec: VisualSpec) -> ValidationResult:
    result = ValidationResult(ok=True, schema=infer_schema(rows))
    chart = get_chart_type(spec.chart_type)
    if not chart:
        result.ok = False
        result.errors.append(f"Unknown chart_type: {spec.chart_type!r}")
        return result
    if not chart.enabled:
        result.ok = False
        result.errors.append(f"Chart type {chart.label!r} is not enabled.")
        return result
    if not rows:
        result.ok = False
        result.errors.append("No result rows to visualise.")
        return result

    columns = _column_set(rows)
    for slot in chart.slots:
        enc = spec.encodings.get(slot.id)
        if slot.required and (enc is None or not enc.field):
            result.ok = False
            result.errors.append(f"Required encoding missing: {slot.label}")
            continue
        if enc is None or not enc.field:
            continue
        if enc.field not in columns:
            result.ok = False
            result.errors.append(f"Column not found: {enc.field!r} ({slot.label})")
            continue
        if not _field_type_ok(rows, enc.field, slot.accepted_types):
            inferred = infer_column_type(rows, enc.field)
            result.ok = False
            result.errors.append(
                f"{enc.field!r} inferred as {inferred}; {slot.label} expects "
                f"{', '.join(sorted(slot.accepted_types))}",
            )

    if spec.chart_type in ("stacked_bar_vertical", "stacked_bar_horizontal"):
        _validate_stacked_bar(rows, spec, result)
    elif spec.chart_type == "scatter":
        _validate_scatter(spec, result)
    elif spec.chart_type == "gantt":
        _validate_gantt(spec, result)

    if not result.errors:
        result.ok = True
    else:
        result.ok = False
    return result


def _validate_stacked_bar(
    rows: Sequence[Mapping[str, Any]],
    spec: VisualSpec,
    result: ValidationResult,
) -> None:
    category_field = spec.encoding_field("category")
    measure_field = spec.encoding_field("measure")
    stack_field = spec.encoding_field("stack")
    if not category_field or not measure_field:
        return

    from ..schema import _cell_value

    categories: list[str] = []
    for row in rows:
        categories.append(str(_cell_value(row, category_field) or "(blank)"))
    counts = Counter(categories)
    dupes = [name for name, count in counts.items() if count > 1]
    if dupes and not stack_field:
        result.ok = False
        preview = ", ".join(dupes[:5])
        suffix = "…" if len(dupes) > 5 else ""
        result.errors.append(
            f"{len(dupes)} categor{'y' if len(dupes) == 1 else 'ies'} have multiple rows but "
            f"Stack / series is not set (e.g. {preview}{suffix}). Fix XQL or assign Stack.",
        )

    if stack_field:
        pair_keys: list[tuple[str, str]] = []
        for row in rows:
            pair_keys.append((
                str(_cell_value(row, category_field) or "(blank)"),
                str(_cell_value(row, stack_field) or "(blank)"),
            ))
        pair_counts = Counter(pair_keys)
        dup_pairs = [key for key, count in pair_counts.items() if count > 1]
        if dup_pairs:
            result.ok = False
            preview = ", ".join(f"{cat}/{stack}" for cat, stack in dup_pairs[:3])
            result.errors.append(
                f"Duplicate category+stack rows ({len(dup_pairs)} pairs, e.g. {preview}). "
                "Aggregate in XQL; the viz layer does not sum.",
            )

    color_field = spec.encoding_field("color")
    if color_field and stack_field and color_field != stack_field:
        result.warnings.append(
            "Colour field differs from Stack; stacked bars use Stack for series colour in v1.",
        )

    limit = int(spec.display.get("limit_categories") or 0)
    if limit and len(counts) > limit:
        result.warnings.append(f"Only top {limit} categories will be shown ({len(counts)} present).")


def _validate_scatter(spec: VisualSpec, result: ValidationResult) -> None:
    if spec.encoding_field("x") and spec.encoding_field("y"):
        return
    result.ok = False
    result.errors.append("Scatter requires X and Y encodings.")


def _validate_gantt(spec: VisualSpec, result: ValidationResult) -> None:
    start = spec.encoding_field("start")
    end = spec.encoding_field("end")
    duration = spec.encoding_field("duration")
    if not start:
        return
    if not end and not duration:
        result.ok = False
        result.errors.append("Gantt requires End or Duration when Start is set.")
    if end and duration:
        result.warnings.append("Both End and Duration set; End takes precedence.")
