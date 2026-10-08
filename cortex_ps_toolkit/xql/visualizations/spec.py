"""Visual specification (encoding map + chart type)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class FieldEncoding:
    field: str
    type: str = "text"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> Optional["FieldEncoding"]:
        if not raw or not raw.get("field"):
            return None
        return cls(field=str(raw["field"]), type=str(raw.get("type") or "text"))

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "type": self.type}


@dataclass
class VisualSpec:
    chart_type: str
    encodings: dict[str, FieldEncoding | None] = field(default_factory=dict)
    label: str = ""
    title: str = ""
    display: dict[str, Any] = field(default_factory=dict)
    query_ref: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VisualSpec":
        enc_raw = raw.get("encodings") if isinstance(raw.get("encodings"), dict) else {}
        encodings: dict[str, FieldEncoding | None] = {}
        for key, value in enc_raw.items():
            encodings[str(key)] = FieldEncoding.from_mapping(value if isinstance(value, dict) else None)
        display = dict(raw.get("display") or {}) if isinstance(raw.get("display"), dict) else {}
        query_ref = dict(raw.get("query_ref") or {}) if isinstance(raw.get("query_ref"), dict) else {}
        return cls(
            chart_type=str(raw.get("chart_type") or ""),
            encodings=encodings,
            label=str(raw.get("label") or ""),
            title=str(raw.get("title") or ""),
            display=display,
            query_ref=query_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "chart_type": self.chart_type,
            "label": self.label,
            "title": self.title,
            "encodings": {
                key: (value.to_dict() if value else None)
                for key, value in self.encodings.items()
            },
            "display": self.display,
            "query_ref": self.query_ref,
        }

    def encoding_field(self, slot_id: str) -> str | None:
        enc = self.encodings.get(slot_id)
        return enc.field if enc else None
