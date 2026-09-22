from __future__ import annotations

from unittest.mock import MagicMock

from playbook_utils.client import PlaybookClient
from playbook_utils.credentials import Credentials, Platform


def _client(platform: Platform) -> PlaybookClient:
    creds = Credentials(
        url="https://example.crtx.test" if platform != Platform.XSIAM else "https://api-tenant.xdr.test",
        key="k",
        api_id="1",
        platform=platform,
    )
    client = PlaybookClient(creds)
    ok = MagicMock()
    ok.ok = True
    ok.status_code = 200
    ok.content = b'"{}"\n'
    ok.json.return_value = "{}"
    ok.text = '"{}"\n'
    client.session = MagicMock()
    client.session.post.return_value = ok
    client.session.delete.return_value = ok
    return client


def test_delete_xsoar6_posts_playbook_delete() -> None:
    client = _client(Platform.XSOAR6)
    client.delete_playbook(playbook_id="abc", name="Main")
    client.session.post.assert_called_once()
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://example.crtx.test/playbook/delete"
    assert kwargs["json"] == {"id": "abc", "name": "Main"}
    assert kwargs["allow_redirects"] is False
    client.session.delete.assert_not_called()


def test_delete_xsoar8_posts_xsoar_playbook_delete_not_public_v1() -> None:
    client = _client(Platform.XSOAR8)
    client.delete_playbook(playbook_id="abc", name="Main")
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://example.crtx.test/xsoar/playbook/delete"
    assert "/public/v1/" not in args[0]
    assert kwargs["json"] == {"id": "abc", "name": "Main"}
    assert kwargs["allow_redirects"] is False
    client.session.delete.assert_not_called()


def test_search_xsiam_posts_xsoar_public_v1_playbook_search() -> None:
    client = _client(Platform.XSIAM)
    client.session.post.return_value.json.return_value = {"playbooks": [], "total": 0}
    client.search_playbooks()
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://api-tenant.xdr.test/xsoar/public/v1/playbook/search"
    assert "/public_api/v1/" not in args[0]
    assert kwargs["json"] == {}
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] >= 300


def test_search_xsoar8_posts_public_v1_playbook_search() -> None:
    client = _client(Platform.XSOAR8)
    client.session.post.return_value.json.return_value = {"playbooks": [], "total": 0}
    client.search_playbooks(query="name:Main")
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://example.crtx.test/xsoar/public/v1/playbook/search"
    assert kwargs["json"] == {"query": "name:Main"}
    assert kwargs["allow_redirects"] is False


def test_unwrap_saved_playbook_xsiam_succeeded_items() -> None:
    from playbook_utils.client import unwrap_saved_playbook

    assert unwrap_saved_playbook({"playbook": {"id": "abc", "name": "Main"}}) == {
        "id": "abc",
        "name": "Main",
    }
    assert unwrap_saved_playbook(
        {"objects_count": 1, "objects": {"succeeded_items": [{"id": "xyz"}]}}
    ) == {"id": "xyz"}
    assert unwrap_saved_playbook({"objects": {"failures_items": [{"error": "nope"}]}}) is None


def test_insert_failure_items_skips_when_succeeded() -> None:
    from playbook_utils.client import insert_failure_items

    assert insert_failure_items(
        {"objects": {"failures_items": [{"error": "already exists"}]}}
    ) == [{"error": "already exists"}]
    assert insert_failure_items(
        {"objects": {"succeeded_items": [{"id": "a"}], "failures_items": [{"error": "x"}]}}
    ) == []


def test_save_script_yaml_xsiam_posts_scripts_insert_zip() -> None:
    import io
    import zipfile

    client = _client(Platform.XSIAM)
    client.save_script_yaml("name: Demo\nscript: print('x')\n", filename="Demo.yml")
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://api-tenant.xdr.test/public_api/v1/scripts/insert"
    uploaded = kwargs["files"]["file"]
    assert uploaded[0] == "Demo.zip"
    assert uploaded[2] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(uploaded[1])) as archive:
        assert "metadata.json" in archive.namelist()
        assert "automation/automation-Demo.yml" in archive.namelist()


def test_save_script_yaml_xsoar6_posts_automation_import() -> None:
    client = _client(Platform.XSOAR6)
    client.save_script_yaml("name: Demo\nscript: print('x')\n", filename="Demo.yml")
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://example.crtx.test/automation/import"
    uploaded = kwargs["files"]["file"]
    assert uploaded[0] == "Demo.yml"
    assert uploaded[2] == "text/yaml"


def test_save_script_yaml_xsoar8_posts_automation_json() -> None:
    client = _client(Platform.XSOAR8)
    client.save_script_yaml(
        "name: Demo\nscript: print('x')\ncommonfields:\n  id: abc\n  version: -1\n",
        filename="Demo.yml",
    )
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://example.crtx.test/xsoar/public/v1/automation"
    assert kwargs["json"]["script"]["name"] == "Demo"
    assert kwargs["headers"]["Content-Type"] == "application/json"


def test_delete_xsiam_posts_playbooks_delete_filter() -> None:
    client = _client(Platform.XSIAM)
    client.delete_playbook(playbook_id="abc")
    args, kwargs = client.session.post.call_args
    assert args[0] == "https://api-tenant.xdr.test/public_api/v1/playbooks/delete"
    assert kwargs["json"] == {
        "request_data": {"filter": {"field": "id", "value": "abc"}}
    }
    assert kwargs["allow_redirects"] is False
