from __future__ import annotations

import json
from unittest.mock import MagicMock

from playbook_utils.client import PlaybookClient
from playbook_utils.credentials import Credentials, Platform
from playbook_utils.lists import copy_list, get_list, save_list, ListRecord


def _client(platform: Platform) -> PlaybookClient:
    creds = Credentials(
        url="https://api-tenant.xdr.test" if platform == Platform.XSIAM else "https://example.crtx.test",
        key="k",
        api_id="1",
        platform=platform,
    )
    client = PlaybookClient(creds)
    client.session = MagicMock()
    return client


def test_get_list_downloads_when_data_missing() -> None:
    client = _client(Platform.XSIAM)
    list_payload = [
        {
            "id": "IssueCategory",
            "name": "IssueCategory",
            "type": "plaintext",
            "version": 2,
        }
    ]

    def side_effect(url, **kwargs):
        response = MagicMock()
        response.ok = True
        if url.endswith("/xsoar/public/v1/lists"):
            response.json.return_value = list_payload
        elif url.endswith("/download/IssueCategory"):
            response.text = "IssueName,Category\nAbnormal,Recon"
        else:
            raise AssertionError(url)
        return response

    client.session.get.side_effect = side_effect
    record = get_list(client, "IssueCategory")
    assert record.name == "IssueCategory"
    assert record.data.startswith("IssueName,Category")


def test_save_list_update_includes_id_and_version() -> None:
    client = _client(Platform.XSOAR8)
    list_payload = [{"id": "IssueCategory", "name": "IssueCategory", "type": "plaintext", "version": 4}]

    def get_side_effect(url, **kwargs):
        response = MagicMock()
        response.ok = True
        response.json.return_value = list_payload
        return response

    def post_side_effect(url, **kwargs):
        response = MagicMock()
        response.ok = True
        response.content = b'{"id":"IssueCategory","version":5}'
        payload = kwargs["json"]
        assert payload["id"] == "IssueCategory"
        assert payload["version"] == 4
        response.json.return_value = {"id": "IssueCategory", "version": 5}
        return response

    client.session.get.side_effect = get_side_effect
    client.session.post.side_effect = post_side_effect
    record = ListRecord(
        id="IssueCategory",
        name="IssueCategory",
        list_type="plaintext",
        version=2,
        data="IssueName,Category",
        meta={"allRead": True, "allReadWrite": True, "propagationLabels": ["all"]},
    )
    saved = save_list(client, record, overwrite=True)
    assert saved["version"] == 5


def test_copy_list_success() -> None:
    source = _client(Platform.XSIAM)
    target = _client(Platform.XSIAM)

    source_list = [
        {
            "id": "Test_Category_List",
            "name": "Test_Category_List",
            "type": "plaintext",
            "version": 2,
            "data": "BU,Category\nBroadBand,Tampering",
            "allRead": True,
            "allReadWrite": True,
            "propagationLabels": ["all"],
        }
    ]

    def source_get(url, **kwargs):
        response = MagicMock()
        response.ok = True
        response.json.return_value = source_list
        return response

    def target_get(url, **kwargs):
        response = MagicMock()
        response.ok = True
        response.json.return_value = []
        return response

    def target_post(url, **kwargs):
        response = MagicMock()
        response.ok = True
        response.content = json.dumps({"id": "Test_Category_List", "version": 1}).encode()
        response.json.return_value = {"id": "Test_Category_List", "version": 1}
        return response

    source.session.get.side_effect = source_get
    target.session.get.side_effect = target_get
    target.session.post.side_effect = target_post

    outcome = copy_list(source, target, "Test_Category_List")
    assert outcome.ok is True
    assert outcome.created is True
    assert outcome.target_id == "Test_Category_List"
