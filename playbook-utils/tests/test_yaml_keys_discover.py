from __future__ import annotations

from playbook_utils.yaml_keys_discover import discover_yaml_keys


EXPORT = """
name: Sample
tasks:
  "39":
    id: "39"
    type: title
    task:
      name: Start Detection Timer
      scriptName: Unused
      iscommand: false
    timertriggers:
    - fieldname: detectionsla
      action: start
    loop:
      iscommand: false
      exitCondition: ""
      wait: 1
  "229":
    id: "229"
    type: collection
    message:
      timings:
        retriescount: 2
        retriesinterval: 360
        completeafterreplies: 1
        completeafterv2: true
    form:
      questions:
      - labelarg:
          simple: Are you or have you at any time used or partook in XSOAR 6.14?
        optionsarg:
        - simple: "Yes"
"""

API = {
    "name": "Sample",
    "tasks": {
        "39": {
            "id": "39",
            "type": "title",
            "task": {"name": "Start Detection Timer", "scriptName": "Unused", "isCommand": False},
            "timerTriggers": [{"fieldName": "detectionsla", "action": "start"}],
            "loop": {"isCommand": False, "exitCondition": "", "wait": 1},
        },
        "229": {
            "id": "229",
            "type": "collection",
            "message": {
                "timings": {
                    "retriesCount": 2,
                    "retriesInterval": 360,
                    "completeAfterReplies": 1,
                    "completeAfterV2": True,
                }
            },
            "form": {
                "questions": [
                    {
                        "labelArg": {
                            "simple": "Are you or have you at any time used or partook in XSOAR 6.14?"
                        },
                        "optionsArg": [{"simple": "Yes"}],
                    }
                ]
            },
        },
    },
}


def test_discover_maps_timer_and_form_keys() -> None:
    result = discover_yaml_keys(EXPORT, API, task_ids=["39", "229"])
    assert result.renames["fieldName"] == "fieldname"
    assert result.renames["labelArg"] == "labelarg"
    assert result.renames["optionsArg"] == "optionsarg"
    assert result.renames["retriesCount"] == "retriescount"
    assert result.renames["completeAfterV2"] == "completeafterv2"
    assert result.renames["isCommand"] == "iscommand"
    assert "scriptName" not in result.renames
    assert "scriptName" in result.preserve
    assert "exitCondition" in result.preserve
    hits = {(h.json_key, h.yaml_key) for h in result.hits if h.json_key != h.yaml_key}
    assert ("fieldName", "fieldname") in hits
    assert ("labelArg", "labelarg") in hits
