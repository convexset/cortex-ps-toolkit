"""Chart type registry: encoding slots per visual type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

SlotKind = Literal["category", "stack", "measure", "x", "y", "start", "end", "duration", "label", "color", "size", "tooltip"]

FieldType = Literal["text", "number", "datetime"]


@dataclass(frozen=True)
class EncodingSlot:
    id: str
    label: str
    kind: SlotKind
    required: bool
    accepted_types: frozenset[str]


@dataclass(frozen=True)
class ChartTypeDefinition:
    id: str
    label: str
    enabled: bool
    slots: tuple[EncodingSlot, ...]
    description: str = ""


CHART_TYPES: tuple[ChartTypeDefinition, ...] = (
    ChartTypeDefinition(
        id="stacked_bar_vertical",
        label="Vertical stacked bar",
        enabled=True,
        description="Category on X; stack segments on Y (long-format rows from XQL).",
        slots=(
            EncodingSlot("category", "Category (X)", "category", True, frozenset({"text"})),
            EncodingSlot("measure", "Measure (Y length)", "measure", True, frozenset({"number"})),
            EncodingSlot("stack", "Stack / series", "stack", False, frozenset({"text"})),
            EncodingSlot("color", "Colour", "color", False, frozenset({"text"})),
            EncodingSlot("tooltip", "Tooltip", "tooltip", False, frozenset({"text", "number", "datetime"})),
        ),
    ),
    ChartTypeDefinition(
        id="stacked_bar_horizontal",
        label="Horizontal stacked bar",
        enabled=True,
        description="Category on Y; stack segments extend on X.",
        slots=(
            EncodingSlot("category", "Category (Y)", "category", True, frozenset({"text"})),
            EncodingSlot("measure", "Measure (X length)", "measure", True, frozenset({"number"})),
            EncodingSlot("stack", "Stack / series", "stack", False, frozenset({"text"})),
            EncodingSlot("color", "Colour", "color", False, frozenset({"text"})),
            EncodingSlot("tooltip", "Tooltip", "tooltip", False, frozenset({"text", "number", "datetime"})),
        ),
    ),
    ChartTypeDefinition(
        id="scatter",
        label="Scatter plot",
        enabled=True,
        description="X and Y from numeric or time columns; optional colour and size.",
        slots=(
            EncodingSlot("x", "X", "x", True, frozenset({"number", "datetime"})),
            EncodingSlot("y", "Y", "y", True, frozenset({"number"})),
            EncodingSlot("color", "Colour", "color", False, frozenset({"text"})),
            EncodingSlot("size", "Size", "size", False, frozenset({"number"})),
            EncodingSlot("tooltip", "Tooltip", "tooltip", False, frozenset({"text", "number", "datetime"})),
        ),
    ),
    ChartTypeDefinition(
        id="gantt",
        label="Gantt",
        enabled=True,
        description="Task label with start/end or start+duration (timestamps from XQL).",
        slots=(
            EncodingSlot("label", "Task label", "label", True, frozenset({"text"})),
            EncodingSlot("start", "Start", "start", True, frozenset({"datetime"})),
            EncodingSlot("end", "End", "end", False, frozenset({"datetime"})),
            EncodingSlot("duration", "Duration", "duration", False, frozenset({"number"})),
            EncodingSlot("color", "Colour", "color", False, frozenset({"text"})),
            EncodingSlot("tooltip", "Tooltip", "tooltip", False, frozenset({"text", "number", "datetime"})),
        ),
    ),
)


def get_chart_type(chart_type_id: str) -> ChartTypeDefinition | None:
    for item in CHART_TYPES:
        if item.id == chart_type_id:
            return item
    return None


def chart_types_for_api() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for chart in CHART_TYPES:
        rows.append({
            "id": chart.id,
            "label": chart.label,
            "enabled": chart.enabled,
            "description": chart.description,
            "slots": [
                {
                    "id": slot.id,
                    "label": slot.label,
                    "kind": slot.kind,
                    "required": slot.required,
                    "accepted_types": sorted(slot.accepted_types),
                }
                for slot in chart.slots
            ],
        })
    return rows


def map_column_type_to_field_type(column_type: str) -> str:
    if column_type in ("integer", "number"):
        return "number"
    if column_type == "timestamp":
        return "datetime"
    return "text"
