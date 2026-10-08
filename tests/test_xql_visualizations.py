from __future__ import annotations

import pytest

from cortex_ps_toolkit.xql.visualizations.render_plotly import render_plotly_figure
from cortex_ps_toolkit.xql.visualizations.spec import FieldEncoding, VisualSpec
from cortex_ps_toolkit.xql.visualizations.validate import validate_visual_spec


def _stacked_spec(*, horizontal: bool, with_stack: bool = True) -> VisualSpec:
    chart = "stacked_bar_horizontal" if horizontal else "stacked_bar_vertical"
    encodings: dict = {
        "category": FieldEncoding(field="incident_type", type="text"),
        "measure": FieldEncoding(field="total_count", type="number"),
    }
    if with_stack:
        encodings["stack"] = FieldEncoding(field="severity", type="text")
    return VisualSpec(chart_type=chart, encodings=encodings, title="Test")


def test_stacked_bar_duplicate_category_without_stack_errors() -> None:
    rows = [
        {"incident_type": "Phishing", "total_count": 1},
        {"incident_type": "Phishing", "total_count": 2},
    ]
    spec = _stacked_spec(horizontal=True, with_stack=False)
    result = validate_visual_spec(rows, spec)
    assert not result.ok
    assert any("Stack / series is not set" in err for err in result.errors)


def test_stacked_bar_horizontal_renders() -> None:
    rows = [
        {"incident_type": "Phishing", "severity": "high", "total_count": 12},
        {"incident_type": "Phishing", "severity": "medium", "total_count": 34},
        {"incident_type": "Malware", "severity": "high", "total_count": 5},
    ]
    spec = _stacked_spec(horizontal=True)
    figure = render_plotly_figure(rows, spec)
    assert figure["data"]
    assert figure["data"][0]["orientation"] == "h"


def test_duplicate_category_stack_pair_errors() -> None:
    rows = [
        {"incident_type": "Phishing", "severity": "high", "total_count": 1},
        {"incident_type": "Phishing", "severity": "high", "total_count": 2},
    ]
    spec = _stacked_spec(horizontal=True)
    result = validate_visual_spec(rows, spec)
    assert not result.ok
    assert any("Duplicate category+stack" in err for err in result.errors)


def test_scatter_renders_numeric_xy() -> None:
    rows = [{"x_val": 1, "y_val": 2}, {"x_val": 3, "y_val": 5}]
    spec = VisualSpec(
        chart_type="scatter",
        encodings={
            "x": FieldEncoding(field="x_val", type="number"),
            "y": FieldEncoding(field="y_val", type="number"),
        },
    )
    figure = render_plotly_figure(rows, spec)
    assert figure["data"][0]["type"] == "scatter"
