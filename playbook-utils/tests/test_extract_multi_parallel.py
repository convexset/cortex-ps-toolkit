"""Unit tests for experimental parallel extract-multi variant."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from playbook_utils.extract_multi_common import ExtractMultiState
from playbook_utils.extract_multi_parallel import (
    _parallel_upload_workers,
    _parallel_workers,
    upload_compare_subplaybooks_parallel,
)


def test_parallel_workers_defaults_to_five() -> None:
    args = argparse.Namespace(parallel_workers=None)
    assert _parallel_workers(args, 12) == 5


def test_parallel_upload_workers_defaults_to_ten() -> None:
    args = argparse.Namespace(parallel_upload_workers=None)
    assert _parallel_upload_workers(args, 20) == 10


def test_parallel_upload_workers_capped_by_job_count() -> None:
    args = argparse.Namespace(parallel_upload_workers=10)
    assert _parallel_upload_workers(args, 3) == 3


def test_parallel_workers_capped_by_job_count() -> None:
    args = argparse.Namespace(parallel_workers=10)
    assert _parallel_workers(args, 3) == 3


@patch("playbook_utils.extract_multi_parallel.insert_failure_items", return_value=[])
@patch("playbook_utils.extract_multi_parallel.unwrap_saved_playbook", return_value={"id": "sub-1"})
def test_parallel_upload_invokes_all_jobs(_mock_unwrap: MagicMock, _mock_failures: MagicMock) -> None:
    client = MagicMock()
    client.save_yaml.return_value = {"playbooks": [{"id": "sub-1", "name": "Sub"}]}
    cache = MagicMock()
    sink = MagicMock()

    jobs = [
        {
            "kind": "root",
            "task_id": "1",
            "subplaybook_name": "Sub A",
            "sub_yaml": "yaml-a",
            "sub": {"name": "Sub A", "tasks": {}},
        },
        {
            "kind": "root",
            "task_id": "2",
            "subplaybook_name": "Sub B",
            "sub_yaml": "yaml-b",
            "sub": {"name": "Sub B", "tasks": {}},
        },
    ]
    args = argparse.Namespace(upload_only=True, parallel_workers=2)
    state = ExtractMultiState(
        args=args,
        creds=MagicMock(platform=MagicMock(value="xsoar8")),
        client=client,
        cache=cache,
        policy=MagicMock(),
        sink=sink,
        playbook={"id": "pb-1", "name": "Main"},
        jobs=jobs,
        result={"extractions": []},
        combined_check=MagicMock(clusters=[]),
        parent_copy_name="Copy",
        task_ids=["1", "2"],
        bind_by_id=False,
        script_names={},
        playbook_names={},
        sub_ids=[None, None],
        execution_variant="parallel",
    )

    exit_code = upload_compare_subplaybooks_parallel(state)
    assert exit_code is None
    assert client.save_yaml.call_count == 2
    assert len(state.result["extractions"]) == 2
