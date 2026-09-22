from cortex_ps_toolkit.playbooks.copy_components import _sub_playbook_refs_ready


def test_sub_playbook_refs_ready_by_planned_source_name() -> None:
    doc = {
        "tasks": {
            "545": {
                "type": "playbook",
                "task": {
                    "playbookId": "3f95cf6c-2015-405b-bf97-7fee6c54d25d",
                },
            }
        }
    }
    ready = _sub_playbook_refs_ready(
        doc,
        pending_source_ids=set(),
        playbook_name_to_id={
            "[REFACTOR-S] [Splunk] Phishing Email Reported by User [INT from 21 to 52]": "35c99fcd-c73a-411c-8725-3d1412ed1c7e",
        },
        playbook_id_remap={},
        playbook_id_to_name={},
        source_names={
            "3f95cf6c-2015-405b-bf97-7fee6c54d25d": "[REFACTOR-S] [Splunk] Phishing Email Reported by User [INT from 21 to 52]",
        },
    )
    assert ready is True
