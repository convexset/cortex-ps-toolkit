from __future__ import annotations

import copy

from playbook_utils.cache import PlaybookCache
from playbook_utils.compare import compare_source_to_downloaded_subplaybook, format_compare_log_line
from playbook_utils.credentials import Credentials, Platform
from tests.test_graph import make_playbook


class _NoNetworkClient:
    def search_playbooks(self, query=None):
        raise AssertionError("compare normalization should not call tenant search")


def _cache_with_sub(name: str, playbook_id: str, tmp_path) -> PlaybookCache:
    creds = Credentials(url="https://example.crtx.test", key="k", api_id="1", platform=Platform.XSOAR8)
    cache = PlaybookCache(creds, _NoNetworkClient(), tmp_path)
    cache._upsert(
        {
            "id": playbook_id,
            "name": name,
            "startTaskId": "0",
            "tasks": {"0": {"id": "0", "type": "start", "task": {"id": "0"}}},
        }
    )
    return cache


def test_compare_normalizes_playbook_name_in_id_field(tmp_path) -> None:
    sub_name = "[BAY] Subplaybook_Phishing_Enrichment"
    sub_id = "51779398-f273-4657-886a-4dc161de55c7"
    cache = _cache_with_sub(sub_name, sub_id, tmp_path)

    source = make_playbook()
    source["tasks"]["4"]["type"] = "playbook"
    source["tasks"]["4"]["task"]["type"] = "playbook"
    source["tasks"]["4"]["task"]["playbookId"] = sub_name
    source["tasks"]["4"]["task"]["playbookName"] = sub_name

    downloaded = copy.deepcopy(source)
    downloaded["tasks"]["4"]["task"]["playbookId"] = sub_id
    downloaded["tasks"]["4"]["task"].pop("playbookName", None)

    compared = compare_source_to_downloaded_subplaybook(source, "1", downloaded, cache=cache)
    assert compared.equal, compared.human_summary()


def test_format_compare_log_line_lists_tasks_and_keys() -> None:
    from playbook_utils.compare import CanonicalGraph, CanonicalNode, CompareResult, PathDiff

    left = CanonicalGraph(
        root_orig_id="366",
        skipped_start_id=None,
        nodes=[
            CanonicalNode(
                index=0,
                orig_id="366",
                type="regular",
                name="Root",
                next_tasks={},
                payload={},
            ),
            CanonicalNode(
                index=1,
                orig_id="325",
                type="playbook",
                name="Call",
                next_tasks={},
                payload={"task": {"playbookId": "a"}},
            ),
        ],
    )
    compared = CompareResult(
        equal=False,
        left_root="366",
        right_root="366",
        left_count=2,
        right_count=2,
        diffs=[PathDiff(path="nodes[1].payload.task.playbookId", left="a", right="b")],
        left=left,
        right=left,
    )
    line = format_compare_log_line(compared, "366")
    assert "tasks=325" in line
    assert "keys=playbookId" in line
    assert "paths=payload.task.playbookId" in line
