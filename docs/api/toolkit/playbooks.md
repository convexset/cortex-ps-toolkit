# Toolkit REST — Playbooks

Wraps tenant playbook search, get, save, and delete using the active credential profile.

## GET /api/playbooks?profile={slug}

Cached playbooks from `data/cache/{cache_key}/playbooks/index.json`.

## POST /api/playbooks/refresh

**Request:** `{ "profile": "psojapac-xsiam" }`

**Response `200`:** `{ "profile", "count", "cache_path", "refreshed_at" }`

## GET /api/playbooks/{playbook_id}/analysis?profile={slug}

Analyze a playbook and reachable sub-playbooks from the tenant cache.

**Response `200`:** structure tree, task breakdown, `scripts_used`, `commands_used`, `copy_scope` (playbook/script ids for component copy), `missing_sub_playbooks`, `notes` (structured warnings/info), `warnings` (flat warning strings for CLI/copy preview).

Optional query/body flags (CLI and WebSocket `playbooks.analyze`): `cache_only`, `skip_cache_refresh` — skips elective **index** refresh; missing playbook YAML and script bodies are still downloaded in parallel from the tenant before analysis runs (see `analysis_body_fetch.ensure_analysis_downloads`).

## GET /api/playbooks/{playbook_id}/analysis/fetch-plan?profile={slug}

Classifies playbook body availability before analysis: counts of index entries vs on-disk bodies, per-id reasons (`missing_file`, `modified_mismatch`, `not_in_index`, …). Used by the analysis panel to show fetch toasts and drive body download progress.

## POST /api/playbooks/refactor/validate-extract

**Request:** `{ "profile", "playbook_id", "kind": "leaf"|"cluster", "task_id" | ("start_id","end_id"), "other_leaf_tasks"?: [] }`

**Response `200`:** `{ "ok", "reasons", … }` from playbook-utils graph rules.

**Cache:** Reads playbook JSON from `data/cache/.../playbooks/bodies/` only (analysis stale policy). **404** if the body is missing — refresh Playbook Tools and re-run analysis first.

**Operation:** `playbooks.refactor.validate_extract`

## POST /api/playbooks/copy-components/preview

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "personal-xsoar6",
  "playbook_id": "<root-uuid>",
  "overwrite": false,
  "stop_on_conflict": false
}
```

**Response:** plan for scripts + playbooks (dependency order), analysis warnings, `would_abort`.

## POST /api/playbooks/copy-components

Same body as preview. Copies referenced scripts first, then sub-playbooks (deepest first), then root; rebinds sub-playbook task `playbookId`/`playbookName` to the target tenant cache before upload.

## POST /api/playbooks/copy/preview

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "personal-xsoar6",
  "playbook_ids": ["<uuid>"],
  "overwrite": false,
  "stop_on_conflict": false
}
```

**Response:** plan with `items[]`, `counts`, `would_abort`, `conflicts`.

## POST /api/playbooks/copy

Same body as preview. Executes copy; returns `results[]` with `status`: `copied`, `updated`, `skipped`.

## POST /api/playbooks/delete/preview

**Request:** `{ "profile": "...", "playbook_ids": ["<uuid>"] }`

## POST /api/playbooks/delete

Same body as preview. Returns per-item `status`: `deleted`, `blocked`, `failed`, `not_found`.

---

## GET /api/playbooks/refactor/presets

List shipped refactor presets (`presets/refactor/*.json`).

## GET /api/playbooks/refactor/presets/{preset_id}

Return one preset (e.g. `mfec-uat-splunk-phishing`).

## POST /api/playbooks/refactor/workflow

Run a workflow preset (clear `[REFACTOR-*]` + one or more refactor steps). Same blocking HTTP semantics as execute.

**Request:**

```json
{
  "preset_id": "mfec-uat-full-workflow",
  "skip_clear": false
}
```

**WebSocket (recommended for long runs):** `playbooks.refactor.workflow` with the same payload. Emits `job.progress` lines during clear and each refactor phase.

**Benchmark:** `python3 scripts/benchmark_mfec_refactor.py --label …` writes timing JSON under `data/refactor-benchmarks/`.

---

## POST /api/playbooks/refactor/preview

Preflight combined refactor (leaf + cluster extracts + optional post-task error-handling specs). **No tenant uploads.** Source playbook loaded from toolkit body cache only; response includes `"cache_only": true`.

**Request:**

```json
{
  "profile": "xsoar-japac-dev",
  "playbook_id": "<uuid>",
  "leaf_tasks": ["366"],
  "clusters": ["21:52"],
  "post_task_updates": ["contains:HttpV2:i|retry=30x30,stop-on-error"],
  "parent_copy_name": null,
  "force": false
}
```

**Response:** `ok`, `reasons`, `extractions[]` with planned `[REFACTOR-S]` / `[REFACTOR-M]` sub-playbook names, `parent_copy_name`, `existing_targets[]` (tenant cache index hits for those names), `overwrite_required`.

**CLI:** `playbooks refactor-preview --profile … --id … --task 366 --cluster 21:52 --post-task-update '…'`

**Tenant API:** Uses playbook-utils cache resolve only (preflight).

**Operation:** `playbooks.refactor.extract_multi` — XSOAR 6/8/XSIAM only.

---

## POST /api/playbooks/refactor/execute

Runs full `extract-multi` (parallel path): **(1)** upload subs in parallel (default **10** upload workers; sub **descriptions included in this YAML**), **(2)** cache refresh, **(3)** sub round-trip compare, **(4)** parent copy upload, **(5)** cache refresh, then optional **post-task updates** (single batch refresh) and **parent** refactor description (in memory / metrics artifacts; no second sub description upload). Legacy `--compare-after-parent` defers step 3 until after the parent upload.

Same request body as preview, plus optional flags: `damp_run`, `upload_only`, `upload_parent_on_mismatch`, `require_match`, `force`, `overwrite_existing`, `overwrite_confirmed`.

`overwrite_existing` defaults to **true** when omitted. When it is true and `existing_targets` is non-empty, the server requires `overwrite_confirmed: true` (UI shows a second confirmation dialog). Overwrite replaces sub-playbooks and the parent copy in place via save/yaml (`prepare_for_overwrite`). At execute time, preflight `existing_targets` (id + name from the toolkit playbooks index) are seeded into the isolated job cache so Phase 1 uploads stamp tenant UUIDs via **index-only** lookup—no per-sub tenant GET or bulk search refresh before all uploads finish. Set `overwrite_existing: false` (UI: uncheck Advanced → overwrite) to reuse same-name playbooks without replacing content — upload may report “already exists” and compare uses the existing body.

**CLI:** `playbooks refactor …`

**Tenant API:** `POST …/playbook/save/yaml` (via playbook-utils).

**UI:** Playbook Tools → Analyze → **Refactor** section. Load presets, preview via HTTP, **Run refactor** streams `job.progress` over WebSocket (falls back to HTTP if WS disconnected).

**WebSocket:** `playbooks.refactor.execute` with the same JSON body as this route. Progress events include upload/compare/description phases from playbook-utils.

---

## POST /api/playbooks/refactor/update-tasks/preview

Preflight in-place task updates (retry/error-handling, context sharing).

**Request:**

```json
{
  "profile": "xsoar-japac-dev",
  "playbook": "Test_PB_Main",
  "name_prefix": "[REFACTOR-S]",
  "updates": ["8:retry=15x45"],
  "context_updates": ["4:global"],
  "match_task_names": ["contains:HttpV2"],
  "match_update": "retry=20x30,stop-on-error"
}
```

**CLI:** `playbooks update-tasks-preview …`

**Operation:** `playbooks.refactor.update_tasks`

---

## POST /api/playbooks/refactor/update-tasks

Same body as preview; optional `dry_run`, `force`. Overwrites existing playbook in place (same id / task ids).

**CLI:** `playbooks update-tasks …`

Reference: [`playbook-utils/AGENTS.md`](../../../../playbook-utils/AGENTS.md)

---

CLI equivalents: [`CONTENT-CLI.md`](../../CONTENT-CLI.md). Master table: [`WEB-API.md`](WEB-API.md).
