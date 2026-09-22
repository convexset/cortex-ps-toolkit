from __future__ import annotations

from playbook_utils.credentials import detect_platform, Platform
from playbook_utils.yaml_codec import dumps_yaml
from tests.test_graph import make_playbook


def test_platform_explicit_xsiam_is_xsiam() -> None:
    assert detect_platform("https://example.local", "xsiam") is Platform.XSIAM


def test_yaml_regular_task_emits_scriptname() -> None:
    import yaml

    text = dumps_yaml(make_playbook())
    inner = yaml.safe_load(text)["tasks"]["1"]["task"]
    assert inner.get("scriptName") == "s-alpha"
    assert "scriptid" not in inner
    assert "scriptId" not in inner


def test_yaml_command_task_emits_script() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["task"]["scriptId"] = "VirusTotal|||ip"
    source["tasks"]["1"]["task"]["isCommand"] = True
    inner = yaml.safe_load(dumps_yaml(source))["tasks"]["1"]["task"]
    assert inner.get("script") == "VirusTotal|||ip"
    assert "scriptid" not in inner
    assert "scriptName" not in inner


def test_yaml_uuid_script_uses_name_catalog() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["task"]["scriptId"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    inner = yaml.safe_load(
        dumps_yaml(source, script_names={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": "CustomPrint"})
    )["tasks"]["1"]["task"]
    assert inner.get("scriptName") == "CustomPrint"


def test_yaml_playbook_task_emits_playbookid_when_binding_by_id() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["type"] = "playbook"
    source["tasks"]["1"]["task"] = {
        "name": "Child",
        "playbookId": "pb-child-id",
        "playbookName": "Child Playbook",
        "type": "playbook",
    }
    inner = yaml.safe_load(
        dumps_yaml(source, bind_subplaybooks_by_id=True)
    )["tasks"]["1"]["task"]
    assert inner.get("playbookid") == "pb-child-id"
    assert inner.get("playbookName") == "Child Playbook"
    assert inner.get("name") == "Child"


def test_yaml_playbook_task_emits_playbookname_with_custom_title_on_xsiam() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["type"] = "playbook"
    source["tasks"]["1"]["task"] = {
        "name": "Enrichment",
        "playbookId": "555b2ec3-613c-4969-842c-567e4d813af5",
        "playbookName": "[BAY] Subplaybook_Phishing_Enrichment",
        "type": "playbook",
    }
    inner = yaml.safe_load(
        dumps_yaml(source, bind_subplaybooks_by_id=True)
    )["tasks"]["1"]["task"]
    assert inner.get("playbookid") == "555b2ec3-613c-4969-842c-567e4d813af5"
    assert inner.get("playbookName") == "[BAY] Subplaybook_Phishing_Enrichment"
    assert inner.get("name") == "Enrichment"


def test_yaml_playbook_task_emits_playbookname() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["type"] = "playbook"
    source["tasks"]["1"]["task"] = {
        "name": "Custom task title",
        "playbookId": "pb-child-id",
        "playbookName": "Child Playbook",
        "type": "playbook",
    }
    inner = yaml.safe_load(dumps_yaml(source))["tasks"]["1"]["task"]
    assert inner.get("playbookName") == "Child Playbook"
    assert inner.get("name") == "Custom task title"
    assert "playbookid" not in inner
    assert "playbookId" not in inner


def test_yaml_playbook_task_uses_cache_name_not_task_title() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["type"] = "playbook"
    source["tasks"]["1"]["task"] = {
        "name": "Enrichment",
        "playbookId": "pb-child-id",
        "type": "playbook",
    }
    inner = yaml.safe_load(
        dumps_yaml(source, playbook_names={"pb-child-id": "[BAY] Subplaybook_Phishing_Enrichment"})
    )["tasks"]["1"]["task"]
    assert inner.get("playbookName") == "[BAY] Subplaybook_Phishing_Enrichment"
    assert inner.get("name") == "Enrichment"


def test_yaml_timer_and_form_keys_are_lowercased() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["timerTriggers"] = [{"fieldName": "detectionsla", "action": "start"}]
    source["tasks"]["1"]["form"] = {
        "questions": [
            {
                "labelArg": {"simple": "Are you on-prem?"},
                "optionsArg": [{"simple": "Yes"}, {"simple": "No"}],
            }
        ]
    }
    source["tasks"]["1"]["message"] = {
        "timings": {
            "retriesCount": 2,
            "retriesInterval": 360,
            "completeAfterReplies": 1,
            "completeAfterV2": True,
        }
    }
    loaded = yaml.safe_load(dumps_yaml(source))["tasks"]["1"]
    assert loaded["timertriggers"][0]["fieldname"] == "detectionsla"
    assert "fieldName" not in loaded["timertriggers"][0]
    assert loaded["form"]["questions"][0]["labelarg"]["simple"] == "Are you on-prem?"
    assert loaded["form"]["questions"][0]["optionsarg"][0]["simple"] == "Yes"
    timings = loaded["message"]["timings"]
    assert timings["retriescount"] == 2
    assert timings["retriesinterval"] == 360
    assert timings["completeafterreplies"] == 1
    assert timings["completeafterv2"] is True
    assert loaded["task"]["scriptName"] == "s-alpha"


def test_yaml_preserves_field_mapping_and_rewrites_field_id() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["fieldMapping"] = [
        {"fieldId": "name", "output": {"simple": "${incident.name}"}}
    ]
    loaded = yaml.safe_load(dumps_yaml(source))["tasks"]["1"]
    assert loaded["fieldMapping"][0]["incidentfield"] == "name"
    assert "fieldId" not in loaded["fieldMapping"][0]
    assert "fieldmapping" not in loaded


def test_yaml_preserves_loop_exit_condition_case() -> None:
    import yaml

    source = make_playbook()
    source["tasks"]["1"]["loop"] = {"isCommand": False, "exitCondition": "", "wait": 1}
    loaded = yaml.safe_load(dumps_yaml(source))["tasks"]["1"]["loop"]
    assert loaded["exitCondition"] == ""
    assert loaded["iscommand"] is False


def test_xsiam_zip_roundtrip() -> None:
    from playbook_utils.client import decode_playbook_payload, yaml_to_zip_bytes

    text = dumps_yaml(make_playbook())
    zipped = yaml_to_zip_bytes(text, filename="Main.yml")
    loaded = decode_playbook_payload(zipped)
    assert loaded["name"] == "Main"
    assert "1" in loaded["tasks"]


def test_xsiam_zip_prefers_yaml_over_metadata_json() -> None:
    """XSIAM GET returns metadata.json first; that file has empty id/name."""
    import io
    import zipfile

    from playbook_utils.client import decode_playbook_payload

    yaml_text = dumps_yaml(make_playbook())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", '{"id": "", "name": ""}')
        archive.writestr("playbook/playbook-Main.yml", yaml_text)
    loaded = decode_playbook_payload(buffer.getvalue())
    assert loaded["name"] == "Main"
    assert loaded.get("id")
