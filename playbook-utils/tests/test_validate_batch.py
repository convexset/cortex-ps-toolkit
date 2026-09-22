from __future__ import annotations

import json
from pathlib import Path

from playbook_utils.validate_batch import job_source_ref, job_task_id, job_upload_names, load_jobs, merge_job_manifests


def test_load_jobs_array(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps([{"task_id": "1", "subplaybook_name": "sub"}]), encoding="utf-8")
    jobs = load_jobs(path)
    assert len(jobs) == 1
    assert jobs[0]["task_id"] == "1"


def test_load_jobs_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [{"task_id": "2"}]}), encoding="utf-8")
    jobs = load_jobs(path)
    assert jobs[0]["task_id"] == "2"


def test_merge_job_manifests(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps([{"task_id": "1"}]), encoding="utf-8")
    b.write_text(json.dumps([{"task_id": "2"}]), encoding="utf-8")
    merged = merge_job_manifests([a, b])
    assert [item["task_id"] for item in merged] == ["1", "2"]


def test_job_helpers() -> None:
    job = {
        "source_playbook": {"name": "Main PB", "id": "abc"},
        "task_id": "7",
        "subplaybook_name": "[REFACTOR-SUBPLAYBOOK] Main",
        "parent_copy_name": "[REFACTOR] Main [at ts]",
    }
    assert job_source_ref(job) == "Main PB"
    assert job_task_id(job) == "7"
    assert job_upload_names(job) == ("[REFACTOR-SUBPLAYBOOK] Main", "[REFACTOR] Main [at ts]")
