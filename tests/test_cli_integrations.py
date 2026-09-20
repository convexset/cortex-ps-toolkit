from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

from cortex_ps_toolkit.cli import build_parser
from cortex_ps_toolkit.cli_content import _cmd_delete_preview, _cmd_refresh


def test_integrations_copy_preview_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "integrations",
            "copy-preview",
            "--from-profile",
            "src",
            "--to-profile",
            "dst",
            "--id",
            "CustomInt",
            "--overwrite",
        ]
    )
    assert args.integrations_command == "copy-preview"
    assert args.from_profile == "src"
    assert args.to_profile == "dst"
    assert args.id == ["CustomInt"]
    assert args.overwrite is True


@patch("cortex_ps_toolkit.cli_content.print_json")
def test_integrations_delete_preview_command(mock_print) -> None:
    mock_plan = MagicMock(return_value={"profile": "lab", "counts": {"delete": 0}})
    resource = MagicMock(plan_delete=mock_plan)
    args = argparse.Namespace(profile="lab", id=["CustomInt"])
    code = _cmd_delete_preview(resource, args)
    assert code == 0
    mock_plan.assert_called_once_with("lab", ["CustomInt"])
    mock_print.assert_called_once()


@patch("cortex_ps_toolkit.cli_content.print_json")
def test_integrations_refresh_command(mock_print) -> None:
    mock_refresh = MagicMock(return_value={"profile": "lab", "instances": {"count": 1}})
    resource = MagicMock(refresh=mock_refresh)
    args = argparse.Namespace(profile="lab")
    code = _cmd_refresh(resource, args)
    assert code == 0
    mock_refresh.assert_called_once_with("lab")
    payload = mock_print.call_args.args[0]
    assert payload["profile"] == "lab"
