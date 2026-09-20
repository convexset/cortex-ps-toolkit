from __future__ import annotations

import time
from pathlib import Path

from scripts.cleanup_playbook_utils_cache import cleanup_job_caches


def test_cleanup_job_caches_removes_old_directories(tmp_path: Path, monkeypatch) -> None:
    jobs = tmp_path / "playbook-utils-cache" / "jobs" / "wf" / "step-a"
    jobs.mkdir(parents=True)
    old = time.time() - (10 * 86400)
    for path in [jobs, jobs.parent, jobs.parent.parent, jobs.parent.parent.parent]:
        path.touch()
    import os

    os.utime(jobs, (old, old))

    monkeypatch.setattr(
        "scripts.cleanup_playbook_utils_cache.playbook_utils_cache_dir",
        lambda: tmp_path / "playbook-utils-cache",
    )

    summary = cleanup_job_caches(max_age_days=7.0, dry_run=False)
    assert summary["removed"] >= 1
    assert not jobs.exists()
