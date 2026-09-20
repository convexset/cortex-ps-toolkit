from __future__ import annotations

from unittest.mock import patch

import pytest

from cortex_ps_toolkit.lists.api import build_update_list_payload
from cortex_ps_toolkit.lists.copy import (
    _classify_copy_action,
    copy_lists_to_tenant,
    list_data_needs_download,
    normalize_list_data,
    plan_lists_copy,
    resolve_list_entry,
)


def test_normalize_list_data_string() -> None:
    assert normalize_list_data("a\nb") == "a\nb"


def test_normalize_list_data_array() -> None:
    assert normalize_list_data(["a", "b"]) == "a\nb"


def test_normalize_list_data_empty_values() -> None:
    assert normalize_list_data([]) == ""
    assert normalize_list_data(None) == ""
    assert normalize_list_data("") == ""


def test_list_data_needs_download() -> None:
    assert list_data_needs_download({"data": None}) is True
    assert list_data_needs_download({"data": ""}) is True
    assert list_data_needs_download({"truncated": True, "data": "x"}) is True
    assert list_data_needs_download({"data": []}) is False


@patch("cortex_ps_toolkit.lists.copy.resolve_list_meta")
def test_resolve_list_entry_empty_cached_list(mock_resolve_meta: object) -> None:
    mock_resolve_meta.return_value = {"id": "1", "name": "Empty", "data": []}
    entry = resolve_list_entry("src", "1")
    assert entry["data"] == ""


@patch("cortex_ps_toolkit.lists.copy.get_profile")
@patch("cortex_ps_toolkit.lists.copy.api.download_list_data")
@patch("cortex_ps_toolkit.lists.copy.resolve_list_meta")
def test_resolve_list_entry_empty_download(
    mock_resolve_meta: object,
    mock_download: object,
    mock_get_profile: object,
) -> None:
    profile = type("P", (), {"slug": "src"})()
    mock_get_profile.return_value = profile
    mock_resolve_meta.return_value = {"id": "1", "name": "Empty", "data": ""}
    mock_download.return_value = []
    entry = resolve_list_entry("src", "1")
    assert entry["data"] == ""
    mock_download.assert_called_once_with(profile, "1")


def test_build_update_list_payload_allows_empty_data() -> None:
    payload = build_update_list_payload(
        {
            "id": "1",
            "version": 2,
            "name": "Empty",
            "data": "old",
            "type": "plain_text",
        },
        {"data": ""},
    )
    assert payload["data"] == ""


@pytest.mark.parametrize(
    ("existing", "overwrite", "stop_on_conflict", "expected"),
    [
        (None, False, False, "copy"),
        ({"id": "1"}, False, False, "skip"),
        ({"id": "1"}, True, False, "update"),
        ({"id": "1"}, False, True, "conflict"),
    ],
)
def test_classify_copy_action(
    existing: dict[str, str] | None,
    overwrite: bool,
    stop_on_conflict: bool,
    expected: str,
) -> None:
    assert (
        _classify_copy_action(
            existing=existing,
            overwrite=overwrite,
            stop_on_conflict=stop_on_conflict,
        )
        == expected
    )


@patch("cortex_ps_toolkit.lists.copy.refresh_lists_cache")
@patch("cortex_ps_toolkit.lists.copy.resolve_list_meta")
@patch("cortex_ps_toolkit.lists.copy.find_list_in_index")
@patch("cortex_ps_toolkit.lists.copy.get_profile")
def test_plan_lists_copy_stop_on_conflict(
    mock_get_profile: object,
    mock_find: object,
    mock_resolve_meta: object,
    mock_refresh: object,
) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": object()})()
    target = type("P", (), {"slug": "tgt", "tenant_type": object()})()
    mock_get_profile.side_effect = [source, target]

    mock_resolve_meta.side_effect = [
        {"id": "a", "name": "Alpha"},
        {"id": "b", "name": "Beta"},
    ]

    def _find(profile: object, *, list_id: str | None = None, name: str | None = None) -> dict | None:
        if name == "Beta":
            return {"id": "existing-beta", "name": "Beta"}
        return None

    mock_find.side_effect = _find

    with patch("cortex_ps_toolkit.lists.copy.assert_operation_supported"):
        plan = plan_lists_copy("src", "tgt", ["a", "b"], stop_on_conflict=True)

    mock_refresh.assert_called_once_with(target)
    assert plan["would_abort"] is True
    assert plan["counts"] == {"total": 2, "copy": 1, "update": 0, "skip": 0, "conflict": 1}
    assert plan["conflicts"] == [
        {"list_id": "b", "name": "Beta", "action": "conflict", "target_id": "existing-beta"},
    ]


@patch("cortex_ps_toolkit.lists.copy.plan_lists_copy")
@patch("cortex_ps_toolkit.lists.copy.get_profile")
def test_copy_lists_aborts_on_conflict(mock_get_profile: object, mock_plan: object) -> None:
    source = type("P", (), {"slug": "src", "tenant_type": object()})()
    target = type("P", (), {"slug": "tgt", "tenant_type": object()})()
    mock_get_profile.side_effect = [source, target]
    mock_plan.return_value = {
        "would_abort": True,
        "conflicts": [{"name": "Beta"}],
    }

    with patch("cortex_ps_toolkit.lists.copy.assert_operation_supported"):
        result = copy_lists_to_tenant("src", "tgt", ["b"], stop_on_conflict=True)

    assert result["aborted"] is True
    assert "Beta" in result["reason"]
    assert result["results"] == []
