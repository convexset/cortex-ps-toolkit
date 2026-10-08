# Bundles — Agent Guide

**Start here** for extended workflow bundle copy, export, and web UI behaviour.

Human overview: [`BUNDLES.md`](BUNDLES.md). REST shapes: [`api/toolkit/bundles.md`](api/toolkit/bundles.md).

---

## Quick paths

| Task | Where |
| --- | --- |
| Plan / execute copy | `cortex_ps_toolkit/bundles/copy.py` — `plan_bundle_copy`, `copy_bundle_to_tenant` |
| ZIP export | `cortex_ps_toolkit/bundles/export.py` |
| Dependency scan | `cortex_ps_toolkit/bundles/dependencies.py` |
| REST | `cortex_ps_toolkit/server/bundles_api.py` |
| Web UI | `web/static/bundles-ui.js`, `web/static/copy-result-ui.js` (`presentBundleCopyResultView`) |
| Resolve basket on source | `design_content/bundle_presets.py` — `resolve_bundle_items` |
| Design phase | `design_content/orchestrator.py` — `execute_cross_tenant_workflow` |
| Portable YAML | `playbooks/portable_yaml.py`, `scripts/portable_yaml.py`, `integrations/portable_yaml.py` |
| Copy notifications flatten | `server/copy_notifications.py` — `_iter_copy_result_entries` |
| Success row semantics | `design_content/copy_progress.py` — `copy_entry_succeeded` |

---

## Copy payload (API / WS)

Required: `source_profile`, `target_profile`, `items[]` with `asset`, `id`, `name`.

Common optional: `overwrite`, `stop_on_conflict`, `copy_mode`, `rename_suffix`, `rename_map`, `shallow_playbooks` (default true), `post_copy_diff` (execute only).

Integrations: `integration_copy_plan_kwargs()` — no rename.

---

## Post-copy diff

Enabled only on scripts, playbooks, lists phases inside `copy_bundle_to_tenant`. Top-level `copy_diff_report` / merged `post_copy_diff_summary` built in `content/post_copy_diff.py` — `finalize_bundle_copy_diff_metadata()`.

UI diff panel: `web/static/copy-diff-panel-ui.js` — `extractCopyDiffRows()` walks nested `results`.

---

## Tests

```bash
python3 -m pytest tests/test_bundle_integrations.py tests/test_bundle_export.py \
  tests/test_copy_notifications.py tests/test_bundle_copy_diff.py -q
```

---

## Related agent guides

| Guide | Path |
| --- | --- |
| Toolkit root | [`../AGENTS.md`](../AGENTS.md) |
| Lists | [`LISTS-AGENTS.md`](LISTS-AGENTS.md) |
| Portable export fields | [`PORTABLE_EXPORT_FIELDS.md`](PORTABLE_EXPORT_FIELDS.md) |
