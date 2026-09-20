#!/usr/bin/env python3
"""Prune stale playbook-utils job cache directories under data/playbook-utils-cache/jobs/."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cortex_ps_toolkit.playbooks.refactor_bridge import playbook_utils_cache_dir


def _dir_age_days(path: Path) -> float:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0
    return max(0.0, (time.time() - mtime) / 86400.0)


def cleanup_job_caches(
    *,
    max_age_days: float,
    dry_run: bool = False,
    include_shared: bool = False,
) -> dict[str, int]:
    base = playbook_utils_cache_dir()
    jobs_root = base / "jobs"
    removed = 0
    kept = 0
    bytes_freed = 0

    targets: list[Path] = []
    if jobs_root.is_dir():
        targets.extend(sorted(jobs_root.rglob("*")))
    if include_shared and base.is_dir():
        for child in sorted(base.iterdir()):
            if child.name == "jobs":
                continue
            targets.append(child)

    seen: set[Path] = set()
    for path in targets:
        if not path.is_dir() or path in seen:
            continue
        seen.add(path)
        if path == jobs_root:
            continue
        age = _dir_age_days(path)
        if age < max_age_days:
            kept += 1
            continue
        size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        if dry_run:
            print(f"would remove {path} ({age:.1f} days old, ~{size} bytes)")
        else:
            shutil.rmtree(path, ignore_errors=True)
            print(f"removed {path} ({age:.1f} days old, ~{size} bytes)")
        removed += 1
        bytes_freed += size

    return {"removed": removed, "kept": kept, "bytes_freed": bytes_freed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-age-days",
        type=float,
        default=7.0,
        help="Remove job cache directories older than this many days (default: 7)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List directories that would be removed")
    parser.add_argument(
        "--include-shared",
        action="store_true",
        help="Also consider top-level cache dirs outside jobs/ (use with care)",
    )
    args = parser.parse_args()
    summary = cleanup_job_caches(
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
        include_shared=args.include_shared,
    )
    print(
        f"Summary: removed={summary['removed']} kept={summary['kept']} "
        f"bytes_freed={summary['bytes_freed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
