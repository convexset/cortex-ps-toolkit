"""Unit tests for playbook refactor bridge and planning."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortex_ps_toolkit.credentials import CredentialProfile
from cortex_ps_toolkit.platforms import Platform, UnsupportedOperation
from cortex_ps_toolkit.playbooks import refactor as refactor_mod
from cortex_ps_toolkit.playbooks.refactor_bridge import (
    _ensure_imported,
    playbook_utils_root,
    profile_credentials_payload,
)


def _profile(platform: Platform = Platform.XSOAR8) -> CredentialProfile:
    return CredentialProfile(
        id="id-1",
        label="Lab",
        slug="lab",
        url="https://tenant.example.test",
        api_id="99",
        key="secret",
        tenant_type=platform,
        verify_ssl=True,
    )


def test_playbook_utils_root_exists() -> None:
    root = playbook_utils_root()
    assert (root / "playbook_utils").is_dir()


def test_profile_credentials_payload() -> None:
    payload = profile_credentials_payload(_profile())
    assert payload["url"] == "https://tenant.example.test"
    assert payload["key"] == "secret"
    assert payload["tenant_type"] == "xsoar8"
    assert payload["api_id"] == "99"


def test_plan_refactor_requires_operations() -> None:
    with pytest.raises(ValueError, match="At least one leaf"):
        refactor_mod.plan_refactor("lab", playbook_id="pb-1", leaf_tasks=[], clusters=[])


@patch("cortex_ps_toolkit.playbooks.refactor.playbook_utils_runtime")
def test_plan_refactor_returns_extractions(mock_runtime: MagicMock) -> None:
    profile = _profile()
    mock_runtime.return_value.__enter__.return_value = (profile, None, None, MagicMock(), None)

    fake_playbook = {
        "id": "pb-1",
        "name": "Main PB",
        "tasks": {
            "10": {"id": "10", "type": "regular", "task": {"name": "Leaf Task"}},
            "20": {"id": "20", "type": "regular", "task": {"name": "Start"}},
            "30": {"id": "30", "type": "regular", "task": {"name": "End"}},
        },
        "startTaskId": "10",
    }
    cache = mock_runtime.return_value.__enter__.return_value[3]
    cache.resolve.return_value = fake_playbook

    _ensure_imported()
    with patch("playbook_utils.graph.check_combined_extract") as mock_check:
        cluster_check = MagicMock(
            start_task_id="20",
            end_task_id="30",
            to_dict=lambda: {"start": "20", "end": "30"},
        )
        root_check = MagicMock(descendant_ids=["10"])
        combined = MagicMock(ok=True, reasons=[], clusters=[cluster_check], root_checks=[root_check])
        mock_check.return_value = combined

        plan = refactor_mod.plan_refactor(
            "lab",
            playbook_id="pb-1",
            leaf_tasks=["10"],
            clusters=["20:30"],
        )

    assert plan["ok"] is True
    assert plan["source_playbook"]["name"] == "Main PB"
    assert len(plan["extractions"]) == 2
    assert plan["extractions"][0]["kind"] == "cluster"
    assert plan["extractions"][1]["kind"] == "leaf"


def test_xdr5_refactor_unsupported() -> None:
    with patch("cortex_ps_toolkit.playbooks.refactor.get_profile", return_value=_profile(Platform.XDR5)):
        with pytest.raises(UnsupportedOperation):
            refactor_mod.execute_refactor("lab", playbook_id="pb-1", leaf_tasks=["1"])


@patch("cortex_ps_toolkit.playbooks.refactor.read_debug_result", return_value={"ok": True})
@patch("cortex_ps_toolkit.playbooks.refactor.build_extract_multi_args")
@patch("cortex_ps_toolkit.playbooks.refactor.temporary_credentials_file")
@patch("cortex_ps_toolkit.playbooks.refactor.get_profile", return_value=_profile())
@patch("cortex_ps_toolkit.playbooks.refactor._ensure_imported")
def test_execute_refactor_parallel_mode(
    _mock_import: MagicMock,
    _mock_profile: MagicMock,
    mock_creds: MagicMock,
    mock_build_args: MagicMock,
    _mock_read: MagicMock,
) -> None:
    mock_creds.return_value.__enter__.return_value = MagicMock()
    mock_build_args.return_value = MagicMock()
    cli_mod = MagicMock()
    cli_mod.cmd_extract_multi.return_value = 0
    import sys

    sys.modules["playbook_utils.cli"] = cli_mod

    refactor_mod.execute_refactor(
        "lab",
        playbook_id="pb-1",
        leaf_tasks=["1"],
        refactor_mode="parallel",
        job_cache_key="wf/step-a",
    )

    assert mock_build_args.call_args.kwargs.get("parallel") is True
    assert mock_build_args.call_args.kwargs.get("job_cache_key") == "wf/step-a"
    sys.modules.pop("playbook_utils.cli", None)
