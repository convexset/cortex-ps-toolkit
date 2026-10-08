from __future__ import annotations

from cortex_ps_toolkit.xql.visualizations.time_in_system import (
    build_time_in_system_timeline,
    floor_to_hour_ms,
    timeline_to_plotly,
)


def test_floor_to_hour_ms() -> None:
    from datetime import datetime, timezone

    dt = datetime(2023, 10, 1, 8, 35, 0, tzinfo=timezone.utc)
    ms = int(dt.timestamp() * 1000)
    floored = floor_to_hour_ms(ms)
    out = datetime.fromtimestamp(floored / 1000, tz=timezone.utc)
    assert out.hour == 8
    assert out.minute == 0


def test_build_timeline_running_count() -> None:
    rows = [
        {
            "xdm.issue.id": "A",
            "create_time": "1696146000000",  # arbitrary ms
            "resolution_time": "1696153200000",
            "duration": 120,
        },
        {
            "xdm.issue.id": "B",
            "create_time": "1696149600000",
            "resolution_time": None,
            "duration": "",
        },
    ]
    points = build_time_in_system_timeline(rows)
    assert points[0].active_count == 0
    assert any(p.tooltip.endswith("created") and p.active_count == 1 for p in points)
    assert any("resolved" in p.tooltip and "A" in p.tooltip for p in points)
    assert points[-1].active_count >= 0


def test_timeline_to_plotly_hv_shape() -> None:
    points = build_time_in_system_timeline([
        {
            "xdm.issue.id": "1",
            "create_time": 1696146000000,
            "resolution_time": 1696153200000,
            "duration": 10,
        },
    ])
    fig = timeline_to_plotly(points)
    assert fig["data"][0]["line"]["shape"] == "hv"
