from cortex_ps_toolkit.core.batch_copy_progress import batch_copy_stages


def test_batch_copy_stages_with_and_without_cache_refresh() -> None:
    assert batch_copy_stages(with_cache_refresh=True)[-1] == "Target Cache Refresh"
    assert batch_copy_stages(with_cache_refresh=False)[-1] == "Finalize Copy"
