"""Time in System — active issue count step line from create/resolution events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def floor_to_hour_ms(timestamp_ms: int) -> int:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    floored = dt.replace(minute=0, second=0, microsecond=0)
    return int(floored.timestamp() * 1000)


@dataclass(frozen=True)
class TimelineEvent:
    timestamp_ms: int
    delta: int
    tooltip: str


@dataclass(frozen=True)
class TimelinePoint:
    timestamp_ms: int
    active_count: int
    tooltip: str


def build_time_in_system_timeline(
    rows: Sequence[Mapping[str, Any]],
    *,
    create_field: str = "create_time",
    resolution_field: str = "resolution_time",
    duration_field: str = "duration",
    id_field: str = "xdm.issue.id",
) -> list[TimelinePoint]:
    """Build step-line points: baseline at floored min(create), +1/-1 events, running total."""
    from ..schema import _cell_value, parse_timestamp

    parsed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        create_ms = parse_timestamp(_cell_value(row, create_field))
        if create_ms is None:
            continue
        resolution_ms = parse_timestamp(_cell_value(row, resolution_field))
        issue_id = _cell_value(row, id_field)
        if issue_id == "" or issue_id is None:
            for alt in ("xdm.case.id", "id"):
                issue_id = _cell_value(row, alt)
                if issue_id != "" and issue_id is not None:
                    break
        if issue_id == "" or issue_id is None:
            issue_id = str(index + 1)
        duration_raw = _cell_value(row, duration_field)
        try:
            duration_minutes = float(duration_raw) if duration_raw != "" else float("nan")
        except (TypeError, ValueError):
            duration_minutes = float("nan")
        parsed.append({
            "create_ms": create_ms,
            "resolution_ms": resolution_ms,
            "issue_id": str(issue_id),
            "duration_minutes": duration_minutes,
        })

    if not parsed:
        return []

    baseline_ms = floor_to_hour_ms(min(item["create_ms"] for item in parsed))
    events: list[TimelineEvent] = [
        TimelineEvent(baseline_ms, 0, "Baseline — active count starts at 0"),
    ]
    for item in parsed:
        issue_id = item["issue_id"]
        events.append(TimelineEvent(
            int(item["create_ms"]),
            1,
            f"Issue {issue_id} created",
        ))
        if item["resolution_ms"] is not None:
            dur = item["duration_minutes"]
            dur_text = "?" if dur != dur else str(int(round(dur)))
            events.append(TimelineEvent(
                int(item["resolution_ms"]),
                -1,
                f"Issue {issue_id} resolved in {dur_text} minutes",
            ))

    events.sort(key=lambda ev: (ev.timestamp_ms, -ev.delta))

    running = 0
    points: list[TimelinePoint] = []
    for ev in events:
        if ev.delta == 0 and not points:
            points.append(TimelinePoint(ev.timestamp_ms, 0, ev.tooltip))
            continue
        running += ev.delta
        points.append(TimelinePoint(ev.timestamp_ms, running, ev.tooltip))

    return points


def timeline_to_plotly(points: Sequence[TimelinePoint]) -> dict[str, Any]:
    """Plotly scatter line with hv shape for step profile."""
    x_iso = [
        datetime.fromtimestamp(p.timestamp_ms / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
        for p in points
    ]
    return {
        "data": [{
            "type": "scatter",
            "mode": "lines",
            "x": x_iso,
            "y": [p.active_count for p in points],
            "text": [p.tooltip for p in points],
            "hovertemplate": "%{text}<extra></extra>",
            "line": {"shape": "hv", "color": "#5b9fd4", "width": 2},
        }],
        "layout": {
            "title": "Time in System — active issues",
            "paper_bgcolor": "#1a222c",
            "plot_bgcolor": "#1a222c",
            "font": {"color": "#e8eef4"},
            "xaxis": {"title": "Event time", "type": "date"},
            "yaxis": {"title": "Active issue count", "rangemode": "tozero"},
            "margin": {"l": 60, "r": 24, "t": 48, "b": 60},
        },
    }
