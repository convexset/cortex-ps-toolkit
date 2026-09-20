from __future__ import annotations

import pytest

from cortex_ps_toolkit.playbooks.post_task_update import (
    parse_post_task_update_spec,
    validate_cluster,
    validate_leaf_task,
    validate_post_task_update_specs,
)


def test_parse_post_task_update_spec_mfec_example() -> None:
    parsed = parse_post_task_update_spec("contains:HttpV2:i|retry=30x30,stop-on-error")
    assert parsed.match_mode == "contains"
    assert parsed.pattern == "HttpV2"
    assert parsed.case_insensitive is True
    assert parsed.retry_count == 30
    assert parsed.retry_interval == 30
    assert parsed.error_handling == "stop-on-error"
    assert parsed.to_spec() == "contains:HttpV2:i|retry=30x30,stop-on-error"


def test_parse_post_task_update_spec_requires_pipe() -> None:
    with pytest.raises(ValueError, match="MATCH\\|actions"):
        parse_post_task_update_spec("contains:HttpV2")


def test_validate_post_task_update_specs_reports_index() -> None:
    errors = validate_post_task_update_specs(["contains:HttpV2|retry=1x5", "bad-spec"])
    assert len(errors) == 1
    assert "rule 2" in errors[0]


def test_validate_cluster_range() -> None:
    assert validate_cluster("21:52") is None
    assert validate_cluster("52:21") is not None
    assert validate_cluster("bad") is not None


def test_validate_leaf_task() -> None:
    assert validate_leaf_task("366") is None
    assert validate_leaf_task("") is not None
