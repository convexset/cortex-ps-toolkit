"""Infer column types from XQL result rows (aligned with xql-monitor.html heuristics)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence

ColumnType = Literal["string", "number", "integer", "timestamp", "empty"]

TYPE_MATCH_RATIO = 0.85
HINTED_TIMESTAMP_RATIO = 0.5

_TIMESTAMP_NAME_HINTS = re.compile(
    r"(^|_)(time|timestamp|date|datetime|created|modified|start|end|ran_at|_time)($|_)",
    re.I,
)


def _cell_value(row: Mapping[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    lower = key.lower()
    for raw_key, value in row.items():
        if str(raw_key).lower() == lower:
            return value
    return ""


def column_name_suggests_timestamp(name: str) -> bool:
    return bool(_TIMESTAMP_NAME_HINTS.search(name))


def parse_timestamp(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{13}", text):
        ms = int(text)
        return ms if ms > 0 else None
    if re.fullmatch(r"\d{10}", text):
        sec = int(text)
        return sec * 1000 if sec >= 946684800 else None
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", text)
    if iso:
        dt = datetime(
            int(iso.group(1)),
            int(iso.group(2)),
            int(iso.group(3)),
            int(iso.group(4)),
            int(iso.group(5)),
            int(iso.group(6)),
        )
        return int(dt.timestamp() * 1000)
    months = {
        "jan": 0, "feb": 1, "mar": 2, "apr": 3, "may": 4, "jun": 5,
        "jul": 6, "aug": 7, "sep": 8, "oct": 9, "nov": 10, "dec": 11,
    }
    match = re.match(
        r"^([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})(?:\s+UTC)?$",
        text,
    )
    if match:
        month = months.get(match.group(1).lower())
        if month is None:
            return None
        dt = datetime(
            int(match.group(3)),
            month + 1,
            int(match.group(2)),
            int(match.group(4)),
            int(match.group(5)),
            int(match.group(6)),
        )
        return int(dt.timestamp() * 1000)
    return None


def _is_integer_like(value: Any) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return abs(numeric - round(numeric)) < 1e-9


def sample_column_values(rows: Sequence[Mapping[str, Any]], column_key: str, limit: int = 80) -> list[Any]:
    values: list[Any] = []
    for row in rows:
        value = _cell_value(row, column_key)
        if value != "" and value is not None:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def infer_column_type(rows: Sequence[Mapping[str, Any]], column_key: str) -> ColumnType:
    values = sample_column_values(rows, column_key)
    name_hint = column_name_suggests_timestamp(column_key)
    if not values:
        return "timestamp" if name_hint else "empty"
    timestamp_count = 0
    integer_count = 0
    numeric_count = 0
    for value in values:
        if parse_timestamp(value) is not None:
            timestamp_count += 1
        try:
            float(value)
            numeric_count += 1
            if _is_integer_like(value):
                integer_count += 1
        except (TypeError, ValueError):
            pass
    total = len(values)
    if timestamp_count / total >= TYPE_MATCH_RATIO:
        return "timestamp"
    if name_hint and timestamp_count > 0 and timestamp_count / total >= HINTED_TIMESTAMP_RATIO:
        return "timestamp"
    if name_hint and timestamp_count == total:
        return "timestamp"
    if integer_count / total >= TYPE_MATCH_RATIO:
        return "integer"
    if numeric_count / total >= TYPE_MATCH_RATIO:
        return "number"
    return "string"


def infer_schema(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            text = str(key)
            if text not in seen:
                seen.add(text)
                keys.append(text)
    out: list[dict[str, Any]] = []
    for key in keys:
        col_type = infer_column_type(rows, key)
        values = sample_column_values(rows, key, limit=200)
        distinct = len({str(v) for v in values})
        out.append({
            "field": key,
            "type": col_type,
            "distinct_count": distinct,
            "null_or_empty_rate": 1.0 - (len(values) / max(len(rows), 1)),
        })
    return out
