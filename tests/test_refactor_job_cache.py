"""Per-job playbook-utils cache directory isolation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.playbooks.refactor_bridge import (
    build_extract_multi_args,
    playbook_utils_job_cache_dir,
    resolve_playbook_utils_cache_dir,
)


def test_playbook_utils_job_cache_dir_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cortex_ps_toolkit.playbooks.refactor_bridge.playbook_utils_cache_dir",
        lambda: tmp_path / "playbook-utils-cache",
    )
    dir_a = playbook_utils_job_cache_dir("mfec-uat-full-workflow/mfec-uat-splunk-phishing")
    dir_b = playbook_utils_job_cache_dir("mfec-uat-full-workflow/mfec-uat-sim-phishing")
    assert dir_a != dir_b
    assert dir_a.is_dir()
    assert dir_b.is_dir()
    assert str(dir_a).startswith(str(tmp_path / "playbook-utils-cache" / "jobs"))


def test_resolve_playbook_utils_cache_dir_default(tmp_path, monkeypatch) -> None:
    base = tmp_path / "playbook-utils-cache"
    monkeypatch.setattr(
        "cortex_ps_toolkit.playbooks.refactor_bridge.playbook_utils_cache_dir",
        lambda: base,
    )
    assert resolve_playbook_utils_cache_dir() == base


def test_build_extract_multi_args_uses_job_cache_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "cortex_ps_toolkit.playbooks.refactor_bridge.playbook_utils_cache_dir",
        lambda: tmp_path / "playbook-utils-cache",
    )
    profile = MagicMock()
    profile.tenant_type.value = "xsiam"
    profile.verify_ssl = True
    args = build_extract_multi_args(
        credentials_path="/tmp/creds.json",
        profile=profile,
        playbook="Main PB",
        leaf_tasks=["1"],
        job_cache_key="wf/step-a",
    )
    expected = playbook_utils_job_cache_dir("wf/step-a")
    assert args.cache_dir == str(expected)


def test_build_extract_multi_args_explicit_cache_dir(tmp_path) -> None:
    profile = MagicMock()
    profile.tenant_type.value = "xsiam"
    profile.verify_ssl = True
    custom = tmp_path / "custom-cache"
    args = build_extract_multi_args(
        credentials_path="/tmp/creds.json",
        profile=profile,
        playbook="Main PB",
        cache_dir=custom,
    )
    assert args.cache_dir == str(custom.resolve())
