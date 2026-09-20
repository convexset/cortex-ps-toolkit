from __future__ import annotations

from unittest.mock import patch

from cortex_ps_toolkit.xql.service import _parse_stream_rows, run_xql_query


def test_parse_stream_rows_jsonl() -> None:
    raw = b'{"a": 1}\n{"a": 2}\n'
    rows = _parse_stream_rows(raw)
    assert rows == [{"a": 1}, {"a": 2}]


@patch("cortex_ps_toolkit.xql.service.api.get_query_results")
@patch("cortex_ps_toolkit.xql.service.api.start_xql_query")
@patch("cortex_ps_toolkit.xql.service.get_profile")
def test_run_xql_query_inline_results(mock_get_profile, mock_start, mock_poll) -> None:
    profile = type("P", (), {"slug": "lab-xsiam"})()
    mock_get_profile.return_value = profile
    mock_start.return_value = ("query-123", 200)
    mock_poll.return_value = (
        {
            "status": "SUCCESS",
            "number_of_results": 1,
            "results": {"data": [{"event_id": "1"}]},
        },
        200,
    )

    result = run_xql_query("lab-xsiam", query="dataset = xdr_data | limit 1")
    assert result["query_id"] == "query-123"
    assert result["row_count"] == 1
    assert result["rows"][0]["event_id"] == "1"


@patch("cortex_ps_toolkit.xql.service.api.get_query_results")
@patch("cortex_ps_toolkit.xql.service.api.start_xql_query")
@patch("cortex_ps_toolkit.xql.service.get_profile")
def test_run_xql_query_passes_timeframe_milliseconds(mock_get_profile, mock_start, mock_poll) -> None:
    profile = type("P", (), {"slug": "lab-xsiam"})()
    mock_get_profile.return_value = profile
    mock_start.return_value = ("query-123", 200)
    mock_poll.return_value = (
        {"status": "SUCCESS", "number_of_results": 0, "results": {"data": []}},
        200,
    )

    run_xql_query(
        "lab-xsiam",
        query="dataset = issues | limit 1",
        timeframe={"relativeTime": 345_600_000},
    )

    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["timeframe"] == {"relativeTime": 345_600_000}
