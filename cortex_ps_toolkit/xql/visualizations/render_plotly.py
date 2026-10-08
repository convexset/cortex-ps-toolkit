"""Build Plotly figure JSON from rows + VisualSpec (no aggregation)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ..schema import _cell_value, parse_timestamp
from .spec import VisualSpec
from .validate import validate_visual_spec

PLOT_COLORS = [
    "#5b9fd4", "#7dd3a8", "#f07178", "#e6c07b", "#c678dd",
    "#56b6c2", "#d19a66", "#98c379", "#61afef", "#be5046",
]


def _numeric(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:
        return None
    return num


def _category_order(rows: Sequence[Mapping[str, Any]], spec: VisualSpec) -> list[str]:
    category_field = spec.encoding_field("category")
    measure_field = spec.encoding_field("measure")
    if not category_field or not measure_field:
        return []
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        cat = str(_cell_value(row, category_field) or "(blank)")
        measure = _numeric(_cell_value(row, measure_field))
        if measure is None:
            continue
        totals[cat] += measure
    ordered = sorted(totals.keys(), key=lambda key: totals[key], reverse=True)
    limit = int(spec.display.get("limit_categories") or 20)
    return ordered[:limit]


def _stacked_bar_figure(
    rows: Sequence[Mapping[str, Any]],
    spec: VisualSpec,
    *,
    horizontal: bool,
) -> dict[str, Any]:
    category_field = spec.encoding_field("category") or ""
    measure_field = spec.encoding_field("measure") or ""
    stack_field = spec.encoding_field("stack")
    categories = _category_order(rows, spec)
    cat_index = {name: idx for idx, name in enumerate(categories)}

    if stack_field:
        series_values: set[str] = set()
        for row in rows:
            series_values.add(str(_cell_value(row, stack_field) or "(blank)"))
        series_order = sorted(series_values)
        traces: list[dict[str, Any]] = []
        for series_idx, series_name in enumerate(series_order):
            values = [0.0] * len(categories)
            for row in rows:
                if str(_cell_value(row, stack_field) or "(blank)") != series_name:
                    continue
                cat = str(_cell_value(row, category_field) or "(blank)")
                if cat not in cat_index:
                    continue
                measure = _numeric(_cell_value(row, measure_field))
                if measure is None:
                    continue
                values[cat_index[cat]] = measure
            trace: dict[str, Any] = {
                "name": series_name,
                "type": "bar",
                "marker": {"color": PLOT_COLORS[series_idx % len(PLOT_COLORS)]},
            }
            if horizontal:
                trace["x"] = values
                trace["y"] = categories
                trace["orientation"] = "h"
            else:
                trace["x"] = categories
                trace["y"] = values
            traces.append(trace)
    else:
        values = [0.0] * len(categories)
        for row in rows:
            cat = str(_cell_value(row, category_field) or "(blank)")
            if cat not in cat_index:
                continue
            measure = _numeric(_cell_value(row, measure_field))
            if measure is None:
                continue
            values[cat_index[cat]] = measure
        trace = {"name": spec.title or "Measure", "type": "bar", "marker": {"color": PLOT_COLORS[0]}}
        if horizontal:
            trace["x"] = values
            trace["y"] = categories
            trace["orientation"] = "h"
        else:
            trace["x"] = categories
            trace["y"] = values
        traces = [trace]

    measure_label = measure_field
    category_label = category_field
    layout: dict[str, Any] = {
        "title": spec.title or spec.label or "Chart",
        "barmode": "stack",
        "showlegend": bool(stack_field),
        "paper_bgcolor": "#1a222c",
        "plot_bgcolor": "#1a222c",
        "font": {"color": "#e8eef4"},
        "margin": {"l": 60, "r": 24, "t": 48, "b": horizontal and 60 or 120},
        "legend": {"orientation": "h", "y": -0.2},
    }
    if horizontal:
        layout["xaxis"] = {"title": measure_label}
        layout["yaxis"] = {"title": category_label, "autorange": "reversed"}
    else:
        layout["xaxis"] = {"title": category_label, "tickangle": -35}
        layout["yaxis"] = {"title": measure_label}

    return {"data": traces, "layout": layout}


def _scatter_figure(rows: Sequence[Mapping[str, Any]], spec: VisualSpec) -> dict[str, Any]:
    x_field = spec.encoding_field("x") or ""
    y_field = spec.encoding_field("y") or ""
    color_field = spec.encoding_field("color")
    size_field = spec.encoding_field("size")

    xs: list[Any] = []
    ys: list[float] = []
    colors: list[str] = []
    sizes: list[float] = []
    for row in rows:
        raw_x = _cell_value(row, x_field)
        y_val = _numeric(_cell_value(row, y_field))
        if y_val is None:
            continue
        ts = parse_timestamp(raw_x)
        xs.append(ts if ts is not None else _numeric(raw_x) if _numeric(raw_x) is not None else raw_x)
        ys.append(y_val)
        if color_field:
            colors.append(str(_cell_value(row, color_field) or "(blank)"))
        if size_field:
            size_val = _numeric(_cell_value(row, size_field))
            sizes.append(size_val if size_val is not None else 8.0)

    trace: dict[str, Any] = {"type": "scatter", "mode": "markers", "x": xs, "y": ys}
    if color_field:
        trace["marker"] = {"color": colors, "colorscale": "Viridis", "showscale": False}
    elif sizes:
        trace["marker"] = {"size": sizes}
    else:
        trace["marker"] = {"color": PLOT_COLORS[0]}

    layout = {
        "title": spec.title or spec.label or "Scatter",
        "paper_bgcolor": "#1a222c",
        "plot_bgcolor": "#1a222c",
        "font": {"color": "#e8eef4"},
        "xaxis": {"title": x_field},
        "yaxis": {"title": y_field},
    }
    if xs and isinstance(xs[0], int):
        layout["xaxis"]["type"] = "date"
    return {"data": [trace], "layout": layout}


def _gantt_figure(rows: Sequence[Mapping[str, Any]], spec: VisualSpec) -> dict[str, Any]:
    label_field = spec.encoding_field("label") or ""
    start_field = spec.encoding_field("start") or ""
    end_field = spec.encoding_field("end")
    duration_field = spec.encoding_field("duration")
    color_field = spec.encoding_field("color")

    labels: list[str] = []
    starts: list[Any] = []
    durations_ms: list[float] = []
    colors: list[str] = []

    for row in rows:
        label = str(_cell_value(row, label_field) or "(blank)")
        start_ms = parse_timestamp(_cell_value(row, start_field))
        if start_ms is None:
            continue
        end_ms = parse_timestamp(_cell_value(row, end_field)) if end_field else None
        if end_ms is None and duration_field:
            dur = _numeric(_cell_value(row, duration_field))
            if dur is not None:
                end_ms = start_ms + int(dur * 1000) if dur < 1e6 else start_ms + int(dur)
        if end_ms is None or end_ms <= start_ms:
            continue
        labels.append(label)
        starts.append(
            datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        durations_ms.append(float(end_ms - start_ms))
        if color_field:
            colors.append(str(_cell_value(row, color_field) or "(blank)"))

    trace: dict[str, Any] = {
        "type": "bar",
        "orientation": "h",
        "base": starts,
        "x": durations_ms,
        "y": labels,
        "marker": {"color": colors if color_field else PLOT_COLORS[0]},
    }
    layout = {
        "title": spec.title or spec.label or "Gantt",
        "paper_bgcolor": "#1a222c",
        "plot_bgcolor": "#1a222c",
        "font": {"color": "#e8eef4"},
        "xaxis": {"title": "Timeline", "type": "date"},
        "yaxis": {"title": label_field, "autorange": "reversed"},
        "barmode": "overlay",
    }
    return {"data": [trace], "layout": layout}


def render_plotly_figure(rows: Sequence[Mapping[str, Any]], spec: VisualSpec) -> dict[str, Any]:
    validation = validate_visual_spec(rows, spec)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    if spec.chart_type == "stacked_bar_vertical":
        return _stacked_bar_figure(rows, spec, horizontal=False)
    if spec.chart_type == "stacked_bar_horizontal":
        return _stacked_bar_figure(rows, spec, horizontal=True)
    if spec.chart_type == "scatter":
        return _scatter_figure(rows, spec)
    if spec.chart_type == "gantt":
        return _gantt_figure(rows, spec)
    raise ValueError(f"Unsupported chart_type: {spec.chart_type}")
