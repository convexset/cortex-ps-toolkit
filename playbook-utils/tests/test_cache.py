from __future__ import annotations

import json
from pathlib import Path

from playbook_utils.cache import PlaybookCache
from playbook_utils.client import PlaybookApiError
from playbook_utils.credentials import Credentials, Platform, detect_platform, load_credentials


class FakeClient:
    def __init__(self, playbooks):
        self.playbooks = playbooks
        self.search_calls = 0
        self.get_calls = []

    def search_playbooks(self, query=None):
        self.search_calls += 1
        return {"playbooks": self.playbooks}

    def get_playbook(self, playbook_id: str):
        self.get_calls.append(playbook_id)
        for item in self.playbooks:
            if item["id"] == playbook_id:
                return item
        raise PlaybookApiError(f"missing {playbook_id}", status_code=404)


def test_detect_platform_from_url() -> None:
    assert detect_platform("https://api-xsoar-japac-test.crtx.au.paloaltonetworks.com") is Platform.XSOAR8
    assert detect_platform("https://api-tenant.xdr.au.paloaltonetworks.com") is Platform.XSIAM
    assert detect_platform("https://10.192.55.11") is Platform.XSOAR6


def test_load_credentials(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    path.write_text(json.dumps({"url": "https://example.crtx.test", "id": 9, "key": "secret"}), encoding="utf-8")
    creds = load_credentials(str(path))
    assert creds.platform is Platform.XSOAR8
    assert creds.api_id == "9"
    assert creds.key == "secret"
    assert "example.crtx.test" in creds.cache_key
    assert creds.cache_key.endswith("/xsoar8")


def test_cache_key_segregates_hosts() -> None:
    a = Credentials(url="https://tenant-a.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    b = Credentials(url="https://tenant-b.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    c = Credentials(url="https://tenant-a.crtx.test", key="k", api_id="1", platform=Platform.XSIAM)
    assert a.cache_key != b.cache_key
    assert a.cache_key != c.cache_key
    assert a.cache_key == "tenant-a.crtx.test/xsoar8"


def test_resolve_index_only_never_calls_tenant(tmp_path: Path) -> None:
    creds = Credentials(
        url="https://example.crtx.test",
        key="k",
        api_id="1",
        platform=Platform.XSOAR8,
    )
    client = FakeClient([])
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cache._upsert(
        {
            "id": "aaa",
            "name": "Target Sub",
            "startTaskId": "0",
            "tasks": {"0": {"id": "0", "type": "start", "task": {"id": "0"}}},
        }
    )
    row = cache.resolve_index_only("Target Sub")
    assert row == {"id": "aaa", "name": "Target Sub"}
    assert client.search_calls == 0
    assert client.get_calls == []


def test_cache_refresh_resolve_and_ttl(tmp_path: Path) -> None:
    creds = Credentials(
        url="https://example.crtx.test",
        key="k",
        api_id="1",
        platform=Platform.XSOAR8,
    )
    playbooks = [
        {"id": "aaa", "name": "One", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
        {"id": "bbb", "name": "Two", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
    ]
    client = FakeClient(playbooks)
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cache.refresh()
    assert cache.is_fresh()
    found = cache.resolve("Two")
    assert found["id"] == "bbb"
    by_id = cache.resolve("aaa")
    assert by_id["name"] == "One"
    assert client.search_calls == 1


def test_find_by_name_prefix_is_case_sensitive(tmp_path: Path) -> None:
    creds = Credentials(url="https://example.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    playbooks = [
        {"id": "p1", "name": "[REFACTOR] Main", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
        {"id": "s1", "name": "[REFACTOR-SUBPLAYBOOK] Main [from A]", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
        {"id": "x1", "name": "[refactor] lower", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
        {"id": "d1", "name": "Default", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
    ]
    cache = PlaybookCache(creds, FakeClient(playbooks), tmp_path, ttl_seconds=3600)
    cache.refresh()
    hits = cache.find_by_name_prefix("[REFACTOR")
    assert {row["id"] for row in hits} == {"p1", "s1"}


def test_cache_invalidates_on_upload(tmp_path: Path) -> None:
    creds = Credentials(url="https://example.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    client = FakeClient(
        [{"id": "aaa", "name": "One", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}}]
    )
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cache.refresh()
    assert cache.meta() is not None
    cache.on_upload()
    assert cache.meta() is None
    assert not cache.is_fresh()
    cache.get("aaa", force=True)
    assert cache.meta() is not None
    assert not cache.meta().complete
    assert not cache.is_fresh()
    manifest = cache.build_manifest()
    assert manifest["count"] == 1
    assert manifest["tenant"]["tenant_type"] == "xsoar8"


def test_xsiam_refresh_uses_search(tmp_path: Path) -> None:
    creds = Credentials(url="https://api-tenant.xdr.test", key="k", api_id="1", platform=Platform.XSIAM)
    playbooks = [
        {"id": "xsiam-1", "name": "X", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
    ]
    client = FakeClient(playbooks)
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cached = cache.refresh()
    assert len(cached) == 1
    assert cached[0]["id"] == "xsiam-1"
    assert client.search_calls == 1
    assert cache.is_fresh()
    assert cache.meta() is not None
    assert cache.meta().complete


def test_xsiam_redownload_after_save_uses_search_not_get(tmp_path: Path) -> None:
    creds = Credentials(url="https://api-tenant.xdr.test", key="k", api_id="1", platform=Platform.XSIAM)
    original = {"id": "src", "name": "Src", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}}
    created = {
        "id": "sub-1",
        "name": "[REFACTOR-SUBPLAYBOOK] Src [from A]",
        "startTaskId": "0",
        "tasks": {"0": {"id": "0", "type": "start", "task": {}}},
    }
    client = FakeClient([original])
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cache.refresh()
    client.playbooks.append(created)
    loaded = cache.redownload_after_save(playbook_id="sub-1", name=created["name"])
    assert loaded["id"] == "sub-1"
    assert client.search_calls == 2
    assert client.get_calls == []


def test_xsoar_redownload_after_save_gets_by_id(tmp_path: Path) -> None:
    creds = Credentials(url="https://example.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    playbooks = [
        {"id": "aaa", "name": "One", "startTaskId": "0", "tasks": {"0": {"id": "0", "type": "start", "task": {}}}},
    ]
    client = FakeClient(playbooks)
    cache = PlaybookCache(creds, client, tmp_path, ttl_seconds=3600)
    cache.refresh()
    loaded = cache.redownload_after_save(playbook_id="aaa", name="One")
    assert loaded["id"] == "aaa"
    assert client.get_calls == ["aaa"]
