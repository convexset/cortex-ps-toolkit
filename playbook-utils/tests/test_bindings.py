"""Tests for cache-based sub-playbook binding resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

from playbook_utils.bindings import (
    name_to_id_map,
    prepare_playbook_for_yaml_export,
    resolve_playbook_task_bindings,
)
from playbook_utils.cache import PlaybookCache
from playbook_utils.client import PlaybookApiError
from playbook_utils.credentials import Credentials, Platform
from playbook_utils.yaml_codec import dumps_yaml


class FakeClient:
    def __init__(self, playbooks):
        self.playbooks = playbooks

    def search_playbooks(self, query=None):
        return {"playbooks": self.playbooks}

    def get_playbook(self, playbook_id: str):
        for item in self.playbooks:
            if item["id"] == playbook_id:
                return item
        raise PlaybookApiError(f"missing {playbook_id}", status_code=404)


def _cache(tmp_path: Path) -> PlaybookCache:
    creds = Credentials(url="https://example.xdr.test", key="k", api_id="1", platform=Platform.XSIAM)
    playbooks = [
        {
            "id": "555b2ec3-613c-4969-842c-567e4d813af5",
            "name": "Enrichment",
            "startTaskId": "0",
            "tasks": {"0": {"id": "0", "type": "start", "task": {}}},
        }
    ]
    cache = PlaybookCache(creds, FakeClient(playbooks), tmp_path, ttl_seconds=3600)
    cache.refresh()
    return cache


def test_resolve_playbook_id_from_name_only(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    playbook = {
        "tasks": {
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Enrichment",
                    "playbookName": "Enrichment",
                },
            }
        }
    }
    unresolved = resolve_playbook_task_bindings(
        playbook,
        name_to_id=name_to_id_map(cache),
        id_to_name={"555b2ec3-613c-4969-842c-567e4d813af5": "Enrichment"},
    )
    assert unresolved == []
    assert playbook["tasks"]["1"]["task"]["playbookId"] == "555b2ec3-613c-4969-842c-567e4d813af5"


def test_resolve_playbook_name_from_id_not_task_title(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    playbook = {
        "tasks": {
            "325": {
                "type": "playbook",
                "task": {
                    "name": "Enrichment",
                    "playbookId": "555b2ec3-613c-4969-842c-567e4d813af5",
                    "type": "playbook",
                },
            }
        }
    }
    unresolved = resolve_playbook_task_bindings(
        playbook,
        name_to_id=name_to_id_map(cache),
        id_to_name={"555b2ec3-613c-4969-842c-567e4d813af5": "[BAY] Subplaybook_Phishing_Enrichment"},
    )
    inner = playbook["tasks"]["325"]["task"]
    assert unresolved == []
    assert inner["name"] == "Enrichment"
    assert inner["playbookName"] == "[BAY] Subplaybook_Phishing_Enrichment"
    assert inner["playbookId"] == "555b2ec3-613c-4969-842c-567e4d813af5"


def test_prepare_playbook_yaml_binds_by_id_on_xsiam(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    playbook = {
        "name": "Sub",
        "tasks": {
            "1": {
                "type": "playbook",
                "task": {
                    "name": "Enrichment",
                    "playbookName": "Enrichment",
                },
            }
        },
    }
    prepared, meta = prepare_playbook_for_yaml_export(playbook, cache)
    assert meta["unresolved_bindings"] == []
    yaml_text = dumps_yaml(prepared, bind_subplaybooks_by_id=True)
    doc = yaml.safe_load(yaml_text)
    inner = doc["tasks"]["1"]["task"]
    assert inner.get("playbookid") == "555b2ec3-613c-4969-842c-567e4d813af5"
    assert inner.get("playbookName") == "Enrichment"
