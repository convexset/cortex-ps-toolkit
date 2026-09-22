"""Overwrite upload must not trigger tenant GET/refresh during parallel Phase 1."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock

from playbook_utils.extract_multi_common import ExtractMultiState, yaml_for_sub_upload


def test_yaml_for_sub_upload_uses_index_only_for_overwrite_id() -> None:
    cache = MagicMock()
    cache.resolve_index_only.return_value = {"id": "existing-uuid", "name": "Sub A"}
    policy = MagicMock()
    state = ExtractMultiState(
        args=argparse.Namespace(overwrite_existing=True),
        creds=MagicMock(),
        client=MagicMock(),
        cache=cache,
        policy=policy,
        sink=MagicMock(),
        playbook={"id": "src", "name": "Main"},
        jobs=[],
        result={},
        combined_check=MagicMock(),
        parent_copy_name="Copy",
        task_ids=[],
        bind_by_id=True,
        script_names={},
        playbook_names={},
        execution_variant="parallel",
    )
    job = {
        "subplaybook_name": "Sub A",
        "sub": {"name": "Sub A", "tasks": {"0": {"id": "0", "type": "start", "task": {"id": "0"}}}},
    }
    yaml_for_sub_upload(state, job)
    cache.resolve_index_only.assert_called_once_with("Sub A")
    cache.resolve.assert_not_called()


def test_yaml_for_sub_upload_skips_overwrite_id_when_not_indexed() -> None:
    cache = MagicMock()
    cache.resolve_index_only.side_effect = KeyError("missing")
    policy = MagicMock()
    state = ExtractMultiState(
        args=argparse.Namespace(overwrite_existing=True),
        creds=MagicMock(),
        client=MagicMock(),
        cache=cache,
        policy=policy,
        sink=MagicMock(),
        playbook={"id": "src", "name": "Main"},
        jobs=[],
        result={},
        combined_check=MagicMock(),
        parent_copy_name="Copy",
        task_ids=[],
        bind_by_id=False,
        script_names={},
        playbook_names={},
        execution_variant="parallel",
    )
    job = {
        "subplaybook_name": "New Sub",
        "sub": {"name": "New Sub", "tasks": {}},
    }
    text = yaml_for_sub_upload(state, job)
    assert "existing-uuid" not in text
    cache.resolve.assert_not_called()
