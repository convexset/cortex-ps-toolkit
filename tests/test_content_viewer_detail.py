"""Tests for integration/script detail payloads and HTTP routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from cortex_ps_toolkit.integrations.detail import (
    get_integration_commands_detail,
    get_integration_definition_detail,
    get_integration_instance_detail,
    split_commands_document,
    split_instance_document,
    split_integration_definition,
)
from cortex_ps_toolkit.lists.detail import get_list_detail, split_list_document
from cortex_ps_toolkit.scripts.detail import get_script_detail, split_script_document
from cortex_ps_toolkit.server.app import create_app


def test_split_integration_definition_extracts_script() -> None:
    configuration, script = split_integration_definition(
        {
            "id": "Alpha",
            "name": "Alpha",
            "integrationScript": {"type": "python", "script": "print('hi')"},
        }
    )
    assert configuration["integrationScript"]["type"] == "python"
    assert "script" not in configuration["integrationScript"]
    assert script == "print('hi')"


def test_split_script_document_extracts_script_body() -> None:
    configuration, script = split_script_document(
        {"id": "abc", "name": "MyScript", "type": "python", "script": "return_results([])"}
    )
    assert configuration["name"] == "MyScript"
    assert "script" not in configuration
    assert script == "return_results([])"


@patch("cortex_ps_toolkit.integrations.detail._configuration_bodies")
def test_get_integration_definition_detail_from_cache(mock_bodies) -> None:
    mock_bodies.return_value = {
        "Alpha": {
            "id": "Alpha",
            "name": "Alpha",
            "integrationScript": {"type": "python", "script": "from CommonServerPython import *"},
        }
    }
    profile = MagicMock()
    profile.slug = "lab-xsoar8"

    payload = get_integration_definition_detail(profile, "Alpha")

    assert payload["kind"] == "integration_definition"
    assert payload["name"] == "Alpha"
    assert payload["script"].startswith("from CommonServerPython")
    assert "script" not in payload["configuration"]["integrationScript"]


def test_split_instance_document_extracts_parameters() -> None:
    configuration, parameters = split_instance_document(
        {
            "id": "inst-1",
            "name": "Slack_instance_1",
            "brand": "SlackV3",
            "data": [{"name": "url", "display": "Server URL", "value": "https://example.test"}],
        }
    )
    assert configuration["brand"] == "SlackV3"
    assert "data" not in configuration
    assert parameters[0]["name"] == "url"


@patch("cortex_ps_toolkit.integrations.detail._instance_bodies")
def test_get_integration_instance_detail_from_cache(mock_bodies) -> None:
    mock_bodies.return_value = {
        "inst-1": {
            "id": "inst-1",
            "name": "Slack_instance_1",
            "brand": "SlackV3",
            "enabled": "true",
            "data": [{"name": "url", "display": "Server URL"}],
        }
    }
    profile = MagicMock()
    profile.slug = "lab-xsoar8"

    payload = get_integration_instance_detail(profile, "inst-1")

    assert payload["kind"] == "integration_instance"
    assert payload["configuration"]["brand"] == "SlackV3"
    assert payload["parameters"][0]["name"] == "url"
    assert "data" not in payload["configuration"]


def test_split_commands_document_extracts_commands() -> None:
    configuration, commands = split_commands_document(
        {
            "id": "SlackV3",
            "name": "SlackV3",
            "commands": [{"name": "slack-send", "arguments": []}],
        }
    )
    assert configuration["name"] == "SlackV3"
    assert "commands" not in configuration
    assert commands[0]["name"] == "slack-send"


@patch("cortex_ps_toolkit.integrations.detail._command_bodies")
def test_get_integration_commands_detail_from_cache(mock_bodies) -> None:
    mock_bodies.return_value = {
        "SlackV3": {
            "id": "SlackV3",
            "name": "SlackV3",
            "display": "Slack v3",
            "commands": [{"name": "slack-send", "arguments": []}],
        }
    }
    profile = MagicMock()
    profile.slug = "lab-xsoar8"

    payload = get_integration_commands_detail(profile, "SlackV3")

    assert payload["kind"] == "integration_commands"
    assert payload["commands"][0]["name"] == "slack-send"
    assert "commands" not in payload["configuration"]


@patch("cortex_ps_toolkit.scripts.detail.api.get_script")
def test_get_script_detail_splits_body(mock_get_script) -> None:
    mock_get_script.return_value = {
        "id": "script-1",
        "name": "MyScript",
        "type": "python",
        "script": "return_results([])",
    }
    profile = MagicMock()
    profile.slug = "lab-xsoar8"

    payload = get_script_detail(profile, "script-1")

    assert payload["kind"] == "script"
    assert payload["script"] == "return_results([])"
    assert "script" not in payload["configuration"]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@patch("cortex_ps_toolkit.server.integrations_api.get_integration_definition_detail")
def test_api_integration_definition_detail(mock_detail, client: TestClient) -> None:
    mock_detail.return_value = {
        "profile": "lab-xsoar8",
        "id": "Alpha",
        "name": "Alpha",
        "kind": "integration_definition",
        "configuration": {"id": "Alpha", "name": "Alpha"},
        "script": "",
        "script_language": "",
    }
    response = client.get("/api/integrations/definitions/Alpha?profile=lab-xsoar8")
    assert response.status_code == 200
    assert response.json()["name"] == "Alpha"


@patch("cortex_ps_toolkit.server.integrations_api.get_integration_instance_detail")
def test_api_integration_instance_detail(mock_detail, client: TestClient) -> None:
    mock_detail.return_value = {
        "profile": "lab-xsoar8",
        "id": "inst-1",
        "name": "Slack_instance_1",
        "kind": "integration_instance",
        "configuration": {"id": "inst-1", "name": "Slack_instance_1"},
    }
    response = client.get("/api/integrations/instances/inst-1?profile=lab-xsoar8")
    assert response.status_code == 200
    assert response.json()["kind"] == "integration_instance"


def test_split_list_document_extracts_data() -> None:
    configuration, data = split_list_document(
        {
            "id": "InternalDomains",
            "name": "InternalDomains",
            "type": "plain_text",
            "data": "example.com\ninternal.local",
        }
    )
    assert configuration["name"] == "InternalDomains"
    assert "data" not in configuration
    assert data == "example.com\ninternal.local"


@patch("cortex_ps_toolkit.lists.detail.resolve_list_entry")
@patch("cortex_ps_toolkit.lists.detail._find_list_entry")
def test_get_list_detail(mock_find, mock_resolve) -> None:
    mock_find.return_value = {"id": "list-1", "name": "MyList", "type": "plain_text"}
    mock_resolve.return_value = {
        "id": "list-1",
        "name": "MyList",
        "type": "plain_text",
        "data": "alpha\nbeta",
    }
    profile = MagicMock()
    profile.slug = "lab-xsoar8"

    payload = get_list_detail(profile, "list-1")

    assert payload["kind"] == "list"
    assert payload["data"] == "alpha\nbeta"
    assert "data" not in payload["configuration"]


@patch("cortex_ps_toolkit.server.integrations_api.get_integration_commands_detail")
def test_api_integration_commands_detail(mock_detail, client: TestClient) -> None:
    mock_detail.return_value = {
        "profile": "lab-xsoar8",
        "id": "SlackV3",
        "name": "SlackV3",
        "kind": "integration_commands",
        "configuration": {"id": "SlackV3", "name": "SlackV3"},
        "commands": [{"name": "slack-send"}],
    }
    response = client.get("/api/integrations/commands/SlackV3?profile=lab-xsoar8")
    assert response.status_code == 200
    assert response.json()["commands"][0]["name"] == "slack-send"


@patch("cortex_ps_toolkit.server.lists_api.get_list_detail")
def test_api_list_detail(mock_detail, client: TestClient) -> None:
    mock_detail.return_value = {
        "profile": "lab-xsoar8",
        "id": "list-1",
        "name": "MyList",
        "kind": "list",
        "configuration": {"id": "list-1", "name": "MyList", "type": "plain_text"},
        "data": "alpha\nbeta",
        "list_type": "plain_text",
    }
    response = client.get("/api/lists/list-1?profile=lab-xsoar8")
    assert response.status_code == 200
    assert response.json()["data"] == "alpha\nbeta"


@patch("cortex_ps_toolkit.server.scripts_api.get_script_detail")
def test_api_script_detail(mock_detail, client: TestClient) -> None:
    mock_detail.return_value = {
        "profile": "lab-xsoar8",
        "id": "script-1",
        "name": "MyScript",
        "kind": "script",
        "configuration": {"id": "script-1", "name": "MyScript"},
        "script": "return_results([])",
        "script_language": "python",
    }
    response = client.get("/api/scripts/script-1?profile=lab-xsoar8")
    assert response.status_code == 200
    assert response.json()["script"] == "return_results([])"
