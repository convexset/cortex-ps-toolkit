# Changes since initial commit (`f86c91a`)

Unreleased work in the working tree after **Big Initial Commit**. Use this as a release-notes draft until changes are committed and tagged.

---

## Playbook analysis — cache layers and fetch UX

| Layer | Path | Role |
| --- | --- | --- |
| **Index** | `data/cache/{key}/playbooks/index.json` | Metadata from tenant search (id, name, modified, …) |
| **Bodies** | `data/cache/{key}/playbooks/bodies/{id}.json` | Full playbook JSON for analysis, copy planning, refactor reads |

**Behaviour**

- `body_lookup.py` — explicit miss reasons (`missing_file`, `modified_mismatch`, `not_in_index`, …).
- **Analysis stale policy** — when index `modified` changes but id/name still match, reuse the cached body and re-stamp `modified` (avoids redundant tenant GETs after index-only refresh).
- `GET /api/playbooks/{id}/analysis/fetch-plan?profile=` — classifies which bodies are missing vs index-only gaps before a run.
- WebSocket job `playbooks.analyze` — progress for elective body fetch; self-dismissing toasts via `analysis-fetch-ui.js` and `operation-progress-ui.js`.
- `cache_only` analysis mode skips elective tenant refresh (see `analyze_playbook(..., cache_only=True)`).

**Docs:** [`playbook-analysis-ux.md`](playbook-analysis-ux.md), [`api/toolkit/playbooks.md`](api/toolkit/playbooks.md).

---

## Refactor — cache-only reads (validation + preview)

Read-only refactor steps no longer open the separate **playbook-utils** tenant cache (which could trigger bulk `playbook/search` refresh).

| Step | Source | Tenant reads |
| --- | --- | --- |
| `POST …/refactor/validate-extract` | Toolkit body cache | None |
| `POST …/refactor/preview` (`plan_refactor`) | Toolkit body cache | None |
| `POST …/refactor/update-tasks/preview` | Toolkit index + bodies | None |
| `POST …/refactor/execute` | Seeds isolated job cache from toolkit body, then `extract-multi` | Upload/compare only (no bulk index refresh for source) |

Implementation: `cortex_ps_toolkit/playbooks/refactor_cache.py`.

If a body is missing, APIs return **404** with guidance to refresh Playbook Tools and re-run analysis.

**Platform op:** `playbooks.refactor.validate_extract` registered in `platforms.py` (fixes prior “Unknown operation” 404 on validate).

**UI:** Refactor preview and help use app outcome dialogs (not `alert()`); **Check validity** hits validate-extract.

---

## Playbook Tools grid — selection bar

- Selection count badge and **Select visible / Select all / Deselect all** above the main playbooks grid (`index.html`, `content-tools-ui.js`).
- Delete actions remain in the copy panel.

---

## Object Setup — copy bundles by application name

Save/load **Copy Object Bundle** selections keyed by XSOAR application name (dedicated overwrite checkboxes, separate from per-asset copy options).

| REST | Purpose |
| --- | --- |
| `GET /api/object-setup/bundles` | List saved bundles |
| `POST /api/object-setup/bundles` | Save bundle |
| `GET /api/object-setup/bundles/{name}` | Load bundle |
| `POST /api/object-setup/bundles/resolve` | Resolve bundle for copy UI |
| `DELETE /api/object-setup/bundles/{name}` | Delete bundle |

Storage: `data/collections/object_setup_bundles.json`.  
Code: `design_content/bundle_presets.py`, `server/object_setup_bundles_api.py`, `web/static/object-setup-ui.js`.

---

## Copy / cache planning (related)

- Copy and copy-components preview prefer **cached** indexes; stale-cache dialog + refresh with progress (`stale-cache-ui.js`).
- Parallel upload workflow with a single post-mutation cache refresh (object setup / deep copy paths).

---

## Flow graph and task UI (analysis panel)

- Flow graph stays centered on the selected playbook when the panel resizes; start task centered on first open.
- Task list / summary: accordion layout, task name links, HTML sanitization fixes.
- Analysis completion toast; debug binary log truncation for large payloads.

---

## Tests

Unit suite: **437 passed** (1 skipped) with `PYTHONPATH=.` — includes `test_refactor_cache.py`, `test_object_setup_bundle_presets.py`, analysis fetch-plan / body lookup tests.

---

## Doc index updates

| File | Topics added/updated |
| --- | --- |
| This file | Full delta since `f86c91a` |
| [`playbook-analysis-ux.md`](playbook-analysis-ux.md) | Two-layer cache, fetch-plan, refactor cache-only |
| [`api/toolkit/WEB-API.md`](api/toolkit/WEB-API.md) | fetch-plan, validate-extract, object-setup bundles |
| [`api/toolkit/playbooks.md`](api/toolkit/playbooks.md) | fetch-plan, validate-extract, cache-only refactor |
| [`FEATURES.md`](FEATURES.md) | Playbook body cache + refactor read policy |
| [`AGENTS.md`](../AGENTS.md) | Refactor cache-only pointer |
