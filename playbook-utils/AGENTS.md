# Playbook utils — Agent Guide

This file is the **single entry point** for agents working on live XSOAR/XSIAM playbook factoring.

**Read this file first.** Human overview: [`README.md`](README.md). Workspace stub: `ai/guidance-cache/playbook-utils.md`.

Package root: `/Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils` (canonical; `bay/playbook-utils` is a symlink here)

---

## Index

| Go here | When |
| --- | --- |
| [Purpose](#purpose) | What this toolkit does and does not do |
| [Directory map](#directory-map) | Files in this package |
| [Decision tree](#decision-tree) | Which CLI command to run |
| [Setup](#setup) | Install, credentials, tenant type |
| [CLI commands](#cli-commands) | Full command list |
| [Inspect and assert](#inspect-and-assert) | Titles, successor counts, potential-root checks |
| [Playbook analysis](#playbook-analysis) | Search, show-task, branch tracing (agent-friendly summaries) |
| [Potential root (A)](#potential-root-a) | When a leaf task may be extracted |
| [Cluster extract (C)](#cluster-extract-c) | Start→end segment extraction |
| [Canonical compare (B)](#canonical-compare-b) | Round-trip subgraph equality |
| [Extract pipeline](#extract-pipeline) | Single leaf, cluster, and combined multi-extract |
| [Refactor descriptions](#refactor-descriptions) | Playbook-level description text on parent + subs; metrics log |
| [Playbook task updates](#playbook-task-updates) | In-place retry/error-handling + context sharing with task-type checks |
| [Naming and share context](#naming-and-share-context) | Default names and `separateContext` |
| [YAML upload field mapping](#yaml-upload-field-mapping) | API JSON vs `/playbook/save/yaml` keys and structure |
| [Cache](#cache) | On-disk layout, TTL, invalidation |
| [APIs by tenant](#apis-by-tenant) | XSOAR 6 / 8 / XSIAM endpoints |
| [Module map](#module-map) | Python modules |
| [Tests](#tests) | How to run pytest |
| [Workflow checklist](#workflow-checklist) | Agent steps for extract / inspect work |
| [Related docs](#related-docs) | Pointers outside this package |

---

## Purpose

Factor tasks out of a live playbook into new sub-playbooks, then upload a **copy** of the parent that calls them.

- **Analysis** — search task inputs/outputs, full-text find, compact task summaries, condition branch tracing across sub-playbooks (`search-task-inputs`, `search-task-outputs`, `search-tasks`, `show-task`, `trace-branches`).
- **Leaf extract** — one potential-root task + descendants (`extract`, or `extract-multi --task`).
- **Cluster extract** — a start→end task segment including side branches (`extract-multi --cluster START:END`).
- **Combined** — cluster(s) and leaf(es) in one parent copy (`extract-multi`).

- Extract uploads a **copy** of the parent; the original playbook is **never overwritten** by extract.
- **Exception:** `update-playbook-tasks` (alias `update-error-retry`) overwrites the selected playbook in place (same id / task ids).
- Work against **XSOAR 8** (lab), **XSOAR 6**, and **XSIAM**.
- Do **not** print or commit credentials (`url`, `id`, `key`).
- Do **not** remap `scriptId` / `playbookId` **values** across tenants. YAML save still converts those API fields to `scriptName` / `script` / `playbookName` (see [Naming and share context](#naming-and-share-context) / yaml_codec).

---

## Directory map

```
playbook-utils/
├── AGENTS.md                 ← this file (agent entry)
├── README.md                 ← human overview
├── requirements.txt          ← requests, PyYAML
├── examples/field-policy.json
├── playbook_utils/
│   ├── cli.py                ← python3 -m playbook_utils
│   ├── inspect.py            ← task titles, successors, --check
│   ├── playbook_tree.py      ← walk root + sub-playbooks from cache
│   ├── task_input_search.py  ← search-task-inputs
│   ├── task_output_search.py ← search-task-outputs
│   ├── task_text_search.py   ← search-tasks
│   ├── task_summary.py       ← compact task_summary for agent review
│   ├── task_show.py          ← show-task
│   ├── condition_branches.py ← trace-branches
│   ├── graph.py              ← potential-root (A), cluster (C), descendants
│   ├── compare.py            ← canonical compare (B), cluster compare
│   ├── extract.py            ← leaf/cluster sub-playbooks + parent rewrite
│   ├── error_retry.py        ← On Error retry / error-handling read + apply
│   ├── context_sharing.py    ← sub-playbook separateContext read + apply
│   ├── task_checks.py        ← regular-script / playbook task validation
│   ├── delete.py             ← name-prefix match + parent-before-sub delete order
│   ├── cache.py              ← on-disk tenant cache
│   ├── client.py             ← HTTP (search/get/save)
│   ├── credentials.py        ← load creds, detect tenant type
│   ├── yaml_codec.py         ← /playbook/save/yaml payload
│   ├── yaml_keys_discover.py ← tenant YAML export → upload key spellings
│   ├── keys.py               ← camelCase ↔ lowercase YAML aliases
│   ├── fields.py             ← drop/ignore field policy
│   └── debugio.py            ← .debug/ artifacts
└── tests/
```

Runtime dirs (gitignored): `.cache/`, `.debug/`.

---

## Decision tree

```
What do you need?
│
├─ Refresh tenant playbooks into local cache
│   → cache-refresh
│
├─ List cached playbooks
│   → list
│
├─ Confirm a playbook/task title, successor count, potential-root
│   → inspect  (use --check to assert; exit 2 on mismatch)
│
├─ Find tasks whose inputs reference a string (main + sub-playbooks)
│   → search-task-inputs --playbook NAME --contains 'issue.name'
│
├─ Full-text search across task content (main + sub-playbooks)
│   → search-tasks --playbook NAME --contains ResultCondition --name-contains 'Check Result'
│
├─ Show compact task summary by id or name (agent review)
│   → show-task --playbook NAME --task 335
│   → show-task --playbook NAME --name-contains 'Check Result'
│
├─ Find tasks whose outputs reference a string, optionally filtered by script
│   → search-task-outputs --playbook NAME --contains name --script setIssue
│
├─ Trace condition branches and upstream variable assignments
│   → trace-branches --playbook NAME --task 335
│
├─ Only ask “is this task a potential root?”
│   → check-root
│
├─ Compare two potential-root subgraphs
│   → compare
│
├─ Factor one leaf task into a sub-playbook (copy of parent)
│   → extract [--damp-run to delete the copies after compare]
│
├─ Factor cluster(s) and/or leaf task(s) in one parent copy
│   → extract-multi --cluster START:END [--task ID …] [--upload-only]
│   → validate-jobs --jobs .debug/…/00-result.json  (after --upload-only batch)
│
├─ Update retry/error-handling (regular script tasks) or context sharing (playbook tasks)
│   → update-playbook-tasks --playbook NAME --update '8:retry=15x45' --context-update '4:global'
│
├─ Delete playbooks by id/name or name prefix
│   → delete --playbook ID  /  delete --name-prefix '[REFACTOR'
│
├─ Learn YAML upload key spellings from a tenant export
│   → discover-yaml-keys --yaml FILE [--json API.json] [--task ID]
│
└─ Clear or inspect cache metadata
    → cache-status / cache-invalidate
```

---

## Setup

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils
python3 -m pip install -r requirements.txt
python3 -m pip install pytest
```

Credentials JSON (same shape as `bay/sample-credentials.json`):

```json
{
  "url": "https://api-tenant.example.paloaltonetworks.com",
  "id": 123,
  "key": "apikey"
}
```

Lab XSOAR 8 file: `bay/lab-xsoar-credentials.json`. Pass `--tenant-type xsoar8`.

Detection if `--tenant-type` is omitted: `crtx.` → `xsoar8`, `.xdr.` → `xsiam`, else `xsoar6`. Credentials may also include `"tenant_type"` / `"platform"`.

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  <command>
```

---

## CLI commands

| Command | Purpose | Typical exit |
| --- | --- | --- |
| `cache-status` | Freshness, count, path | 0 |
| `cache-invalidate` | Delete this tenant cache | 0 |
| `cache-refresh` | Search + download all playbooks | 0 |
| `list` | Table of cached playbooks | 0 |
| `get PLAYBOOK` | One playbook by id or name | 0 / 1 |
| `inspect` | Titles, total successors, potential-root; `--check` | 0 / 2 |
| `search-task-inputs` | Tasks whose serialized inputs contain a substring (recursive sub-playbooks) | 0 / 1 |
| `search-tasks` | Full-text task search + `task_summary` per match; `--name-contains`; `--format agent\|table` (default **agent**) | 0 / 1 |
| `search-task-outputs` | Tasks whose serialized outputs contain a substring; optional `--script` filter | 0 / 1 |
| `show-task` | Compact task summary by `--task` or `--name-contains` | 0 / 1 |
| `trace-branches` | Branch drivers + assignment `task_summary`; `--format agent\|table` (default **agent**) | 0 |
| `check-root` | Potential-root (A) for one task | 0 / 2 |
| `compare` | Canonical compare (B) of two subgraphs | 0 / 2 |
| `extract` | Build/upload one leaf sub-playbook + parent copy | 0 / 2 |
| `extract-multi` | Cluster and/or leaf extracts → one parent copy | 0 / 2 |
| `validate-jobs` | Re-download and compare jobs from `--upload-only` extract-multi | 0 / 2 |
| `update-playbook-tasks` | Overwrite playbook: retry/error-handling + context sharing (with task-type checks) | 0 / 2 |
| `update-error-retry` | Alias for `update-playbook-tasks` | 0 / 2 |
| `delete` | Delete by id/name or case-sensitive `--name-prefix` | 0 / 1 |
| `discover-yaml-keys` | YAML export vs API JSON: upload key spellings | 0 |

Global flags: `--credentials`, `--tenant-type`, `--insecure`, `--cache-dir`, `--cache-ttl`, `--fields-config`, `--debug-dir`, `--quiet`, `--print-json`.

Every `get` / `inspect` / `search-task-inputs` / `search-task-outputs` / `search-tasks` / `show-task` / `trace-branches` / `check-root` / `compare` / `extract` / `extract-multi` / `validate-jobs` / `delete` / `cache-refresh` / `list` writes JSON + text under `.debug/<timestamp>-…/` unless `--debug-dir` is set.

---

## Inspect and assert

**Total successors** = task ids reachable via `nextTasks` from the selected task, **excluding itself** (BFS order from `descendant_ids`). Direct `nextTasks` count is also reported in JSON as `direct_successor_ids`.

**Potential root** = check (A) below. `inspect` prints `yes`/`no` and leak reasons.

List selected tasks:

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  inspect --playbook Test_PB_Inv_Data_Main --task 7 --task 2 --task 4
```

Assert (repeatable `--check`; comma-separated `key=value`; exit **2** if any fail):

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  inspect --playbook Test_PB_Inv_Data_Main \
  --check '7,name=Print Key_In_Main,successors=2,root=yes' \
  --check '2,name=YES!,successors=3,root=yes' \
  --check '4,name=Test_PB_Inv_Data_Unexpanded_Sub,successors=1,root=no'
```

`--task` on `extract` / `inspect` may be a tasks-map id or a unique task name.

Lab fixture `Test_PB_Inv_Data_Main` is the reference playbook for these three checks.

---

## Playbook analysis

Walk a **root playbook and all reachable sub-playbooks** from the tenant cache (`playbook_tree.walk_playbook_tree`). Run `cache-refresh` first so sub-playbook references resolve.

### Commands

| Command | Purpose | Key flags | Exit |
| --- | --- | --- | ---: |
| `search-task-inputs` | Find tasks that **read** a string (inputs, conditions, messages, …) | `--contains NEEDLE` | 0 / 1 |
| `search-task-outputs` | Find tasks that **write** a string (script args, field mappings) | `--contains NEEDLE`, optional `--script COMMAND` | 0 / 1 |
| `search-tasks` | Full-text search; each match includes **`task_summary`** | `--contains NEEDLE`, optional `--name-contains`, `--format agent\|table` | 0 / 1 |
| `show-task` | Compact summary for one task or all tasks matching a name | `--task ID_OR_NAME` **or** `--name-contains TEXT` | 0 / 1 |
| `trace-branches` | Condition task: branch labels, drivers, upstream assignments | `--task ID_OR_NAME`, `--format agent\|table` | 0 |

**Default output format** for `search-tasks` and `trace-branches` is **`agent`** — compact text with enough context to review without full task JSON. Use `--format table` for the legacy tabular listing (`search-tasks` only).

Add **`--print-json`** (global) to emit JSON on stdout. Otherwise read `.debug/<timestamp>-<command>-…/02-*.json`.

### `task_summary` object (JSON)

Produced by `task_summary.compact_task_summary()` and attached to search matches, `show-task` entries, and branch assignment drivers:

| Field | When present |
| --- | --- |
| `name`, `type` | Always |
| `script` | Regular/command task binding (e.g. `Set`, `Builtin\|\|\|setIssue`) |
| `playbook_ref` | Sub-playbook call node |
| `successors` | `{branch_label: [task_id, …]}` |
| `branches` | Condition tasks — label, condition text, variables, expected values, successors |
| `arguments` | Simplified script args (`set_key`/`set_value` for `Set`; field→value for others) |

Canvas metadata (`view`, `taskId`, versions, …) is stripped from search serialization.

### Branch tracing semantics

`trace-branches` parses each branch on a **condition** task, finds upstream `Set` / `setIssue` / sub-playbook input assignments for branch variables, and includes a **`task_summary`** on each driver task.

When no upstream assignment exists in the playbook tree, the report shows **`start_fallback`** (value assumed from incident/playbook start — often a dead branch or field set outside the tree).

### Agent workflow examples

**Find and review a condition task (e.g. task 335):**

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils

python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  search-tasks \
  --playbook '[Splunk] Phishing Email Reported by User' \
  --contains ResultCondition \
  --name-contains 'Check Result'

python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  show-task \
  --playbook '[Splunk] Phishing Email Reported by User' \
  --task 335

python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  trace-branches \
  --playbook '[Splunk] Phishing Email Reported by User' \
  --task 335
```

**Find where a field is read vs written:**

```bash
python3 -m playbook_utils ... search-task-inputs \
  --playbook '[Splunk] Phishing Email Reported by User' --contains 'issue.name'

python3 -m playbook_utils ... search-task-outputs \
  --playbook '[Splunk] Phishing Email Reported by User' --contains name --script setIssue
```

**Scan write-only incident fields:**

```bash
for field in krungsricategory ncsacategory ncsaasset; do
  python3 -m playbook_utils ... search-tasks \
    --playbook '[Splunk] Phishing Email Reported by User' --contains "$field"
done
```

### Offline vs live

| Source | Tool |
| --- | --- |
| Live tenant cache | This package (`cache-refresh` then analysis commands) |
| Exported YAML on disk | `ai/tools/playbook_yaml/` (`analyze`, `search-tasks`) |

Working notes for BAY Splunk phishing analysis: `bay/scratch/phishing-playbook-facts.md`.

---

## Potential root (A)

A task may be extracted only if:

1. It cannot reach **itself** via `nextTasks` (cycles among *other* descendants are allowed).
2. No **outside** task points at a descendant other than the selected task (incoming edges **to the root** are allowed and are retargeted on extract).

Implementation: `playbook_utils/graph.py` (`check_potential_root`).

---

## Cluster extract (C)

A start/end pair may be extracted only if (`check_cluster_extract` in `graph.py`):

1. **Reachability** — end is reachable from start via `nextTasks`.
2. **No bypass** — no task reachable from start without passing through end (`reachable_without_end` is empty).
3. **Boundary incoming** — no outside task points at a cluster task other than start.
4. **Boundary outgoing** — no outside task is reached from a cluster task other than end (end’s outside successors become the parent call node’s `nextTasks`).
5. **Non-conditional end** — end must not be `type: condition`. Conditional branch labels cannot be represented on a sub-playbook call node the same way.
6. **No overlap** — cluster task set must not intersect any leaf extract in the same `extract-multi` run (`check_combined_extract`).

**Cluster task set** = `desc(start) − desc(end) + {end}` (includes side branches off the main path, e.g. tasks that branch from mid-cluster nodes but still flow to end).

**Parent rewrite** (`rewrite_parent_cluster`):

- Predecessors of start → cluster sub-playbook call node (leaf call, no `nextTasks` on the node itself).
- End’s outside successors → same call node’s `nextTasks` (`separateContext: false`).
- All cluster tasks removed from parent.

**Combined runs** (`rewrite_parent_combined`): clusters first, then leaves. When a leaf extract removes a task that an earlier cluster call still references, `retarget_all_successors` retargets **every** `nextTasks` reference to that task id (not only preflight incoming edges).

Example (BAY XSIAM phishing refactor):

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  extract-multi --playbook '[Splunk] Phishing Email Reported by User' \
  --cluster 21:52 \
  --task 366 --task 368 --task 370 --task 454 --task 372 --task 373
```

Reference outcome: source 146 tasks → parent 72; 7 subs (1 cluster @14 nodes, 6 leaves @81 combined nodes); 7/7 compare pass.

---

## Canonical compare (B)

`extract` **always** diffs the original potential-root subgraph (tasks + `nextTasks` connections) against the **re-downloaded** sub-playbook after upload. Implementation: `compare_source_to_downloaded_subplaybook` in `compare.py`.

- After upload, the sub-playbook is **re-fetched in the same document family as the cache**: XSOAR 6/8 `GET` JSON; XSIAM bulk `POST /xsoar/public/v1/playbook/search` refresh then resolve by name (not YAML ZIP `playbooks/get`).
- Source root = the extracted task. Downloaded root = sub-playbook `start`, which is skipped so comparison begins at the first real task.
- Nodes are linearized (DFS, sorted branch labels); ids / views / versions are ignored by the **policy** compare (`FieldPolicy`). That gate decides whether the parent copy is uploaded.
- Key aliases (`scriptArguments`/`scriptarguments`, `playbookId`/`playbookName`, `Brand|||command`/`|||command`) remain as safety nets when search JSON still differs from YAML-shaped fields. XSOAR 6/8 get is already camelCase JSON, so those mappings are usually no-ops.
- `extract` also writes an **all-fields** compare (`08b-compare-all-fields.txt`) with an empty ignore list, listing every payload difference so ignore/drop keys can be tuned. Summaries include counts by relative path; every diff is listed (no truncation).
- Payloads include inner `task` fields such as `scriptId`, `scriptArguments`, conditions.
- A live lab run that uploaded `scriptid: Print` came back with `scriptId` missing (`'Print' != None`) — that is this check, and it matches the UI (regular tasks with no script bound, arguments hidden).

`--require-match` on `extract` exits 2 on mismatch. `--damp-run` uploads, compares against the re-downloaded sub-playbook, then deletes the created copies and reports the outcome. `--upload-parent-on-mismatch` still writes the parent copy.

---

## Extract pipeline

### Single leaf (`extract`)

1. Select playbook + task
2. Check potential root (A)
3. Build + upload sub-playbook YAML
4. Re-download in cache format (XSOAR GET JSON; XSIAM search refresh) and compare (B) against the source subgraph
5. Build a **new** parent: insert a **leaf** sub-playbook call node at the original task position, retarget incoming edges (and all `nextTasks` refs via `retarget_all_successors`), **remove** extracted descendant tasks
6. Apply playbook-level descriptions to the sub (overwrite) and parent copy when compare matches
7. Upload parent only if compare matches (unless `--upload-parent-on-mismatch`)

### Combined (`extract-multi`)

1. Select playbook + one or more `--cluster START:END` and/or `--task` ids
2. Preflight each cluster (C) and leaf (A); reject overlaps
3. Upload each sub-playbook; on XSIAM resolve assigned `playbookId` from cache after each sub upload
4. Compare each sub (unless `--upload-only`)
5. Rewrite parent once: clusters first (`rewrite_parent_cluster`), then leaves (`rewrite_parent` with `retarget_all_successors`)
6. Optional `--post-task-update MATCH|actions` (repeatable): when all compares pass, apply in-place task updates to each generated sub-playbook **before** the parent upload. Keeps refactor round-trip compares clean — task tuning happens after sub compare, not before.
7. Apply playbook-level **descriptions** to each sub (overwrite) and the parent copy (in YAML): extraction aspects, HttpV2 retry summary (with sub-playbook names on the parent HttpV2 sub-list when tasks live in subs), and **totals-only** refactor metrics on the parent. Preserves an existing source playbook description above a `---` separator. Per-sub metrics and the full totals line are written to `12-refactor-metrics.txt` in the debug folder.
8. Upload parent when all compares pass (unless `--upload-parent-on-mismatch`)

Recommended two-phase workflow when tuning tasks (e.g. HttpV2 retry):

```bash
# Phase 1 — refactor + compare (no task mutations)
python3 -m playbook_utils ... cache-refresh
python3 -m playbook_utils ... extract-multi --playbook '...' --cluster 21:52 --task 366 ...

# Phase 2 — in-place updates on generated subs (or use --post-task-update on extract-multi)
python3 -m playbook_utils ... cache-refresh
python3 -m playbook_utils ... update-playbook-tasks --name-prefix '[REFACTOR-S]' \
  --match-task-name 'contains:HttpV2:i' --match-update 'retry=20x30,stop-on-error'
```

Or combine phase 2 into extract-multi:

```bash
python3 -m playbook_utils ... extract-multi ... \
  --post-task-update 'contains:HttpV2:i|retry=20x30,stop-on-error'
```

`validate-jobs` re-runs step 4 for a prior `--upload-only` result JSON after one cache refresh.

`--skip-parent` uploads only sub-playbook(s). `--damp-run` deletes whatever was uploaded (parent copy first, then subs).

Do not remap script/playbook id **values** across tenants. On **XSIAM**, parent YAML binds sub calls by tenant `playbookid` (`bind_subplaybooks_by_id=True` in `yaml_codec.py`).

---

## Refactor descriptions

After a successful extract (compare passes, parent about to upload), the toolkit writes **playbook-level** `description` fields on each generated sub-playbook and the parent copy. This does **not** modify inner `tasks[id].task.description` fields — those are copied unchanged by `extract.py`.

Implementation: `playbook_utils/refactor_descriptions.py` (`descriptions_for_refactor`, `build_parent_description`, `build_sub_description`, `build_refactor_metrics_log`). Upload helpers: `overwrite_playbook_description` in `playbook_update.py`.

### When descriptions are applied

| Command | Descriptions applied when |
| --- | --- |
| `extract` | Compare matches and parent will upload (same gate as parent YAML upload) |
| `extract-multi` | All sub compares pass, parent will upload, not `--upload-only` |

Skipped when `--upload-only`, compare mismatch (and parent not uploaded), or `--skip-parent` (single extract — no parent description).

On `extract-multi` (parallel path), optional `--post-task-update` runs **after** parent upload and compare, **before** parent description is applied in memory. Sub-playbook **descriptions are embedded in the first sub YAML upload** (HttpV2 lines are predicted from `--post-task-update` specs when present). Sub uploads use **10** parallel workers by default (`DEFAULT_PARALLEL_UPLOAD_WORKERS`; override with `--parallel-upload-workers`). Post-task overwrites defer per-upload cache refresh and validate after one batch refresh.

### Source description preservation

The source playbook’s existing text is resolved from `description`, then legacy `comment`. When present, it is kept at the top of the parent description, followed by a `---` separator, then the refactor block.

### Parent `[REFACTOR-M]` format

```text
<ORIGINAL_DESCRIPTION optional>

---

Automatic Refactor of <SOURCE_PLAYBOOK_NAME>:
 - Cluster Refactor from Task <START> to Task <END> into <SUB_NAME>. Tasks Moved: 21, 22, …
 - Leaf Refactor from Task <N> into <SUB_NAME>. Tasks Moved: …
 - HTTPv2 Task On Error Configuration Set: Up to N retries with retry interval M seconds
    * Task 372 (<SUB_NAME>)
    * Task 373 (<SUB_NAME>)
 …

Refactor Metrics:
 - 81 nodes moved
 - 7 call nodes added
 - 11 incoming links re-written
 - 3 outgoing links re-written
```

Rules:

- **Aspect lines** — one per extraction (clusters first, then leaves; same order as `extract-multi` jobs). Task ids in **Tasks Moved** are sorted numerically; full list (no truncation).
- **HttpV2 block** — only when `--post-task-update` applied retry changes. Parent sub-list includes **sub-playbook name in parentheses** when the task lives in a sub. Omitted entirely when no HttpV2 tasks were updated.
- **Refactor Metrics** — **totals only** on the parent (four bullet lines). Per-sub breakdown is **not** uploaded — tenants may reject overly long descriptions.

### Sub `[REFACTOR-S]` format

```text
Refactored from <SOURCE_PLAYBOOK_NAME>
 - Leaf Refactor from Task <N> into <SUB_NAME>. Tasks Moved: …
 - HTTPv2 Task On Error Configuration Set: Up to N retries with retry interval M seconds
    * Task 372
    * Task 373
```

Rules:

- One aspect line matching that sub’s extraction.
- HttpV2 block only when that sub had matching tasks updated; sub-list uses **task numbers only** (no sub-playbook name).
- No Refactor Metrics section on subs.

### Debug artifacts

Written under `.debug/<timestamp>-extract-…/` (step 12):

| File | Content |
| --- | --- |
| `12-refactor-descriptions.json` | `parent_description`, `sub_descriptions`, `metrics_log`, counts |
| `12-parent-description.txt` | Exact parent text uploaded |
| `12-sub-description-NN.txt` | One file per sub (alphabetical by sub name) |
| `12-refactor-metrics.txt` | **Full** metrics: per-sub lines + combined totals line |

Example metrics log:

```text
Refactor Metrics for [Splunk] Phishing Email Reported by User:
 - [REFACTOR-S] … [INT from 21 to 52]: 14 nodes moved to sub-playbook; 1 sub-playbook call node added to parent; 2 incoming links re-written, 3 outgoing links re-written
 - [REFACTOR-S] … [LEAF from 366]: 7 nodes moved to sub-playbook; …
 …
 - Totals: 81 nodes moved; 7 call nodes added; 11 incoming links re-written, 3 outgoing links re-written
```

### Compare interaction

Subgraph compare (B) ignores playbook-level `description` — description overwrites happen **after** compare and do not affect round-trip equality checks.

### Example: combined extract with HttpV2 + descriptions

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials.json \
  extract-multi --playbook '[Splunk] Phishing Email Reported by User' \
  --cluster 21:52 \
  --task 366 --task 368 --task 370 --task 372 --task 373 --task 454 \
  --post-task-update 'contains:HttpV2:i|retry=30x30,stop-on-error'
```

Stdout summary includes `descriptions ok=True` when all sub description overwrites succeeded.

---

## Playbook task updates

`update-playbook-tasks` overwrites a live playbook via `/playbook/save/yaml` using `prepare_for_overwrite` (preserves playbook id, canvas task ids, inner task UUIDs, and node `taskId`).

### Task-type checks (`task_checks.py`)

| Update | Required task type | Required binding |
| --- | --- | --- |
| `--update` (retry / error handling) | `regular` | `scriptId`, `scriptName`, or `script` on inner task |
| `--context-update` | `playbook` | `playbookName` or `playbookId` on inner task |

Preflight rejects invalid tasks; valid updates in the same command are still applied. Exit **2** if any task is rejected or validation fails.

### Task title matching (`task_match.py`)

Match regular script tasks by title before applying updates:

| Spec | Meaning |
| --- | --- |
| `PATTERN` | `contains`, case-sensitive |
| `contains:PATTERN` | substring match, case-sensitive |
| `contains:PATTERN:i` | substring match, case-insensitive |
| `equals:PATTERN` | exact title, case-sensitive |
| `equals:PATTERN:i` | exact title, case-insensitive |

Use with `update-playbook-tasks`:

```bash
--match-task-name 'contains:HttpV2:i' --match-update 'retry=20x30,stop-on-error'
```

Combine with `--name-prefix` to update many playbooks. Explicit `--update TASK:actions` and `--match-task-name` can be used together.

### On Error retry (regular script tasks)

Observed on XSOAR 8 lab tenant (`Test_PB_Inv_Data_Main`):

| Task | Type | Retry / handling |
| --- | --- | --- |
| 4 Test_PB_Inv_Data_Unexpanded_Sub | `playbook` | N/A — retry updates **rejected** |
| 6 SET Key_In_Main | `regular` | No retry, error path → 10 |
| 8 SET Another_Key | `regular` | Retry via `scriptArguments`; stop on error |

**On Error retry** for script/automation tasks is stored under **`scriptArguments`**, not a separate task-level retry block:

```yaml
scriptarguments:
  retry-count:
    simple: "20"
  retry-interval:
    simple: "60"
```

**Error handling** uses:

| Mode | API JSON |
| --- | --- |
| Stop on error | `continueOnErrorType: ""`, omit `continueOnError` |
| Continue | `continueOnError: true`, `continueOnErrorType: ""` |
| Continue on error path | `continueOnError: true`, `continueOnErrorType: "errorPath"`, `#error#` branch in `nextTasks` |

Collection / communication tasks use `message.timings.retriesCount` / `retriesInterval` (different semantics — not covered yet).

### Context sharing (playbook call tasks)

| Mode | API JSON |
| --- | --- |
| Global / shared incident context | `separateContext: false` |
| Sub-playbook isolated context | `separateContext: true` |

Task 4 (`Test_PB_Inv_Data_Unexpanded_Sub`) defaults to `separateContext: true` (isolated). `--context-update '4:global'` sets shared context.

Regular tasks (e.g. task 8) are **rejected** for context updates.

### CLI

```bash
# Retry: task 4 rejected (playbook), task 8 applied (Set script)
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  update-playbook-tasks --playbook Test_PB_Inv_Data_Main \
  --update '4:retry=15x45' --update '8:retry=15x45'

# Context: task 4 applied (global), task 8 rejected (regular)
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  update-playbook-tasks --playbook Test_PB_Inv_Data_Main \
  --context-update '4:global' --context-update '8:global'
```

- `--update TASK:actions` — `parse_update_spec()` in `error_retry.py`
- `--context-update TASK:global|subplaybook` — `parse_context_update_spec()` in `context_sharing.py`
- `--validate-task ID` — include in before/after report
- `--dry-run` — build upload YAML only
- `update-error-retry` — alias for backward compatibility

Pipeline: load cache → preflight → apply accepted updates → `dumps_yaml(..., overwrite=True)` → `save_yaml` → cache refresh → validate → `.debug/` report.

---

## Naming and share context

Defaults (override leaf sub name on single `extract` with `--sub-playbook-name`; override parent with `--parent-copy-name`):

| Artifact | Pattern |
| --- | --- |
| Leaf sub-playbook | `[REFACTOR-S] {main} [LEAF from {task_id}]` |
| Cluster sub-playbook | `[REFACTOR-S] {main} [INT from {start_id} to {end_id}]` |
| Replacement parent | `[REFACTOR-M] {main} [at {ts}]` |

`{ts}` is UTC ISO to minute precision — no seconds or fractional seconds (`2026-09-09T19:14+00:00`) so repeated extracts sequence readably.

Legacy sub prefixes `[REFACTOR-S-LEAF]`, `[REFACTOR-S-INT]`, and `[REFACTOR-SUBPLAYBOOK]`, plus parent prefix `[REFACTOR]`, are still recognized by `delete` for cleanup.

Share context:

- Sub-playbook **document**: `separateContext: true` → YAML `separatecontext: true`
- Parent **call node**: `separateContext: false` so the nested run shares incident context (`true` on the caller is an isolated context)

Field names, nested timer/form/collection shape, drop/ignore lists, and `scriptId`→`scriptName` rewrites: [YAML upload field mapping](#yaml-upload-field-mapping).

---

## YAML upload field mapping

GET/search playbooks are **camelCase API JSON**. `/playbook/save/yaml` persists **lowercase schema keys** except a short preserve list. Implementation: `keys.yaml_name_for_key` / `rename_known_keys_to_yaml`, `yaml_codec.prepare_for_upload`, `fields.FieldPolicy`.

Live extracts always compare **cached source subgraph vs re-fetched sub-playbook** (policy compare + all-fields `08b`). A camelCase schema key that the save endpoint ignores shows up as `left: value, right: None`.

### Document shape

```
playbook:
  id, name, version: -1, starttaskid, separatecontext, view (JSON string)
  tasks:
    "<id>":
      id, type
      task:                  # inner task
        version: -1
        name, type, description, brand
        scriptName | script | playbookName   # bindings — see below
        iscommand
      nexttasks: { "<label>": ["<id>", ...] }
      scriptarguments: { <argName>: { simple | complex } }
      conditions / loop / message / form / timertriggers / view / …
```

`view` is a JSON **string** in YAML (`position.x` / `position.y`). Playbook input/argument names (`assignBy`, `OnCall`, `GetOriginalEmail`) keep whatever case the playbook already uses.

### Binding rewrites (not case aliases)

| API JSON (`task`) | YAML upload | If omitted / wrong |
| --- | --- | --- |
| `scriptId` (automation) | `scriptName` (catalog name, else the id string). **Delete** `scriptId`. | Save ignores `scriptid`; UI shows a regular task with no script, arguments hidden |
| `scriptId` with `isCommand` or `Brand\|\|\|command` | `script: Brand\|\|\|command`, `iscommand: true`. **Delete** `scriptId`. | Command not bound |
| `playbookId` | `playbookName` (XSOAR) or `playbookid` + `playbookName` (XSIAM). XSOAR: **delete** `playbookId`. XSIAM: keep UUID **and** emit `playbookName` when the canvas task title differs from the sub-playbook name (see BAY exports: custom `name` + `playbookName`). | Sub-playbook call not bound |
| `fieldMapping[].fieldId` | `fieldMapping[].incidentfield` (keep `fieldMapping` camelCase). **Delete** `fieldId`. | Extend-context mapping dropped |

Do **not** remap those **values** across tenants. Same-tenant copies still do this field conversion.

### Keys that stay mixed-case (`YAML_PRESERVE_CASE`)

`scriptName`, `playbookName`, `exitCondition` (under `loop`), `fieldMapping` (extend-context mapping on a task — content YAML keeps this camelCase; `fieldmapping` is dropped on save), `inputSections`, `vcShouldKeepItemLegacyProdMachine`.

### Schema keys lowercased on upload (`_ALIASES` → YAML)

| API JSON | YAML | Where |
| --- | --- | --- |
| `startTaskId` | `starttaskid` | playbook |
| `taskId` | `taskid` | task node (then **dropped** on upload; server assigns a new UUID) |
| `nextTasks` | `nexttasks` | task node |
| `scriptArguments` | `scriptarguments` | task node |
| `separateContext` | `separatecontext` | playbook and task node |
| `continueOnError` / `continueOnErrorType` | `continueonerror` / `continueonerrortype` | task node |
| `timerTriggers` | `timertriggers` | task node |
| `timerTriggers[].fieldName` | `timertriggers[].fieldname` | SLA timer; `action` stays `start`/`stop` |
| `ignoreWorker`, `skipUnavailable`, `quietMode`, `isOverSize`, `isAutoSwitchedToQuietMode` | lowercase | task node |
| `isCommand` | `iscommand` | inner `task` and `loop` |
| `ignoreCase`, `isContext` | `ignorecase`, `iscontext` | conditions / arguments |
| `sourcePlaybookID` | `sourceplaybookid` | playbook |
| `reputationCalc` | `reputationcalc` | task node |
| `defaultAssigneeComplex` | `defaultassigneecomplex` | task node |
| `evidenceData` | `evidencedata` | task node |
| `labelArg`, `optionsArg` | `labelarg`, `optionsarg` | `form.questions[]` |
| `readOnly`, `gridColumns`, `defaultRows`, `fieldAssociated` | `readonly`, `gridcolumns`, `defaultrows`, `fieldassociated` | `form.questions[]` |
| `message.timings.retriesCount` | `retriescount` | collection task |
| `retriesInterval` | `retriesinterval` | collection timings |
| `completeAfterReplies` / `completeAfterV2` / `completeAfterSla` | `completeafterreplies` / `completeafterv2` / `completeaftersla` | collection timings |

Nested collection / timer shape that must survive save:

```
timertriggers:
  - fieldname: detectionsla    # not fieldName
    action: start
message:
  timings:
    retriescount: 2            # not retriesCount
    retriesinterval: 360
    completeafterreplies: 1
    completeafterv2: true
form:
  questions:
    - labelarg: { simple: "…" }     # not labelArg
      optionsarg: [{ simple: "Yes" }]
```

### Dropped on upload (server-owned; do not send)

Playbook: `cacheVersn`, `modified`, `created`, `sizeInBytes`, `packID`, `packName`, `itemVersion`, `fromServerVersion`, `toServerVersion`, `propagationLabels`, `definitionId`, `vcShouldIgnore`, `vcShouldKeepItemLegacyProdMachine`, `commitMessage`, `shouldCommit`, `taskIds`, `sequenceNumber`, `primaryTerm`, `syncHash`, `numericId`, `indexName`, `sortValues`, `highlight`, `isOverridable`, `prevName`, `missingScriptsIds`.

Inner `task`: `id`, `modified`, `created`, `sizeInBytes`, `cacheVersn`, `sequenceNumber`, `primaryTerm`, `numericId`, `syncHash`, `indexName`, `sortValues`, `highlight`. Force `version: -1`.

Task node: `taskId`.

`primaryTerm` + `sequenceNumber` are Elasticsearch `_primary_term` / `_seq_no` concurrency tokens. They change on save (and `primaryTerm` also after cluster failover). They are not playbook logic.

### Ignored by policy compare (upload gate)

Same server-owned keys plus `id`, `taskId`, `view`, `version`, `nameRaw`, `sourcePlaybookID`, pack/system flags, `comment`/`tags`, and form question `id`s (because `id` is stripped at every dict level). **Do not ignore** `fieldName`, `labelArg`, `optionsArg`, `scriptId`/`scriptName`, `scriptArguments`, timings, or `nextTasks` — those are real losses if they mismatch.

All-fields compare (`08b-compare-all-fields.txt`) lists every remaining difference with an empty ignore list.

### Discovering a new spelling

```bash
python3 -m playbook_utils discover-yaml-keys \
  --yaml examples/Phishing_-_Generic_v3_copy.yml \
  --json .cache/<host>/xsoar8/playbooks/<id>.json \
  --task 39 --task 229
```

The tool serializes distinctive API values, finds them in the export text, and reads the adjacent YAML key (including `- fieldname:` list items and nested `simple:` under `labelarg`). Add new **schema** pairs to `_ALIASES` in `keys.py`. Do not blindly lowercase remaining mixed-case keys — playbook inputs keep names like `assignBy`.

---

## Cache

Path: `.cache/<host-url>/<tenant-type>/`  
Example: `.cache/api-xsoar-japac-test.crtx.au.paloaltonetworks.com/xsoar8/`

| Tenant | Bulk list | Notes |
| --- | --- | --- |
| XSOAR 6 / 8 | `cache-refresh` via playbook search | Writes `manifest.json` / `manifest.txt` |
| XSIAM | `cache-refresh` via XSOAR-compat `POST /xsoar/public/v1/playbook/search` | Official public_api has no list. Lab search is large (~30s, tens of MB). Extract re-fetches the new sub from this search JSON (not YAML ZIP). `get --playbook` is still YAML ZIP. |

TTL default 1 hour (`--cache-ttl 0` = until invalidate). Any upload or delete invalidates that tenant cache.

---

## APIs by tenant

| Tenant | List | Get | Save | Delete |
| --- | --- | --- | --- | --- |
| XSOAR 6 | `POST /playbook/search` | `GET /playbook/{id}` (search fallback) | `POST /playbook/save/yaml` | `POST /playbook/delete` body `{"id"}` |
| XSOAR 8 | `POST /xsoar/public/v1/playbook/search` | `GET /xsoar/public/v1/playbook/{id}` | `POST /xsoar/public/v1/playbook/save/yaml` | `POST /xsoar/playbook/delete` body `{"id"}` (not under `/xsoar/public/v1`) |
| XSIAM | `POST /xsoar/public/v1/playbook/search` (undocumented XSOAR-compat; not `/public_api/v1/playbooks/search`) | `POST /public_api/v1/playbooks/get` (YAML ZIP) | `POST /public_api/v1/playbooks/insert` (YAML ZIP) | `POST /public_api/v1/playbooks/delete` body `request_data.filter` |

XSOAR 8 **must not** POST `/xsoar/public/v1/playbook/delete`: that prefix treats `delete` as `{playbook_id}` on the GET-by-id route (HTTP 405). Lab-confirmed path is `/xsoar/playbook/delete`. `DELETE /xsoar/public_api/v1/playbooks` is not a live route on this tenant.

XSIAM playbook docs: https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/playbooks  
XSIAM **list** is not in those docs. Lab-confirmed: `POST /xsoar/public/v1/playbook/search` (also `/xsoar/playbook/search`) returns JSON `{playbooks, tags, total}`. Official `/public_api/v1/playbooks/search` is not a live route (generic 500). Search can take tens of seconds and tens of MB; client timeout is at least 300s.
XSOAR 8 playbook APIs: https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/playbooks

---

## Module map

| File | Role |
| --- | --- |
| `cli.py` | argparse commands |
| `inspect.py` | `inspect_task`, `--check` specs, text report |
| `playbook_tree.py` | Shared root + sub-playbook tree walk |
| `task_input_search.py` | Recursive task-input substring search across sub-playbooks |
| `task_text_search.py` | Full-text task search across sub-playbooks |
| `task_output_search.py` | Recursive task-output substring search with optional script filter |
| `task_summary.py` | Compact `task_summary` for agent review (branches, args, successors) |
| `task_show.py` | `show-task` by id or name |
| `condition_branches.py` | Condition branch parsing + upstream variable assignment tracing |
| `graph.py` | descendants, `total_successors`, potential-root (A), cluster (C), combined preflight |
| `compare.py` | canonical linearization + diff; `compare_source_to_downloaded_cluster_subplaybook` |
| `extract.py` | `build_subplaybook`, `build_subplaybook_cluster`, `rewrite_parent`, `rewrite_parent_cluster`, `rewrite_parent_combined`, `retarget_all_successors`, default names |
| `refactor_descriptions.py` | Parent/sub description builders, totals-only metrics for upload, full metrics log text |
| `playbook_update.py` | `overwrite_playbook_task_updates`, `overwrite_playbook_description` |
| `error_retry.py` | `read_task_error_state`, `apply_playbook_error_updates`, `preflight_error_updates`, `parse_update_spec` |
| `context_sharing.py` | `read_task_context_state`, `apply_playbook_context_updates`, `preflight_context_updates`, `parse_context_update_spec` |
| `task_checks.py` | `check_regular_script_task`, `check_playbook_task`, `has_script_binding` |
| `delete.py` | Prefix match; delete `[REFACTOR-M]` parents before `[REFACTOR-S] …` subs (legacy prefixes too) |
| `yaml_codec.py` | drop metadata, `version: -1`, `scriptId`→`scriptName`/`script`, `prepare_for_overwrite`, alias lowercase schema keys |
| `yaml_keys_discover.py` | tenant YAML export → API key spellings (`discover-yaml-keys`) |
| `keys.py` | `separateContext` ↔ `separatecontext`, `yaml_name_for_key` |
| `cache.py` | disk cache + manifest |
| `client.py` | HTTP + delete + XSIAM ZIP helpers |
| `fields.py` | configurable ignore/drop lists |
| `debugio.py` | debug file sink |

---

## Tests

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils
python3 -m pytest -q
```

Keep tests offline (no live tenant). Use `tests/test_graph.py` `make_playbook()` fixtures.

When adding a CLI flag or extract behaviour, update **both** `README.md` (human) and this file (agent).

---

## Workflow checklist

### Inspect a live playbook

1. `cache-refresh` or `get --playbook` (one-off)
2. `inspect --playbook NAME` to list tasks
3. `inspect --check 'ID,name=…,successors=N,root=yes|no'` to assert
4. Read `.debug/` if the table is not enough

### Analyze branching or field usage

1. `cache-refresh` (sub-playbooks must resolve)
2. `search-tasks --contains …` to locate tasks by text; optional `--name-contains` to narrow by task title
3. `show-task --task ID` for one compact snapshot; `--name-contains` to list matches
4. `trace-branches --task ID` for condition tasks — read driver assignments and `start_fallback` rows
5. Use `search-task-inputs` / `search-task-outputs` when the question is specifically read vs write paths
6. Prefer `--print-json` or `.debug/…/02-*.json` for programmatic follow-up (`task_summary` fields)

### Extract a leaf subgraph

1. `inspect` / `check-root` until the task is a potential root
2. Live `extract` (always uploads; policy compare is against the re-downloaded sub-playbook)
3. `--damp-run` when the copies should be deleted after compare (lab tests)
4. Round-trip mismatches are expected while tuning `FieldPolicy`; use debug dumps

### Extract cluster + leaves (combined)

1. `inspect` the start/end pair — confirm end is not `condition`; check successor counts
2. Confirm no bypass paths (end must be on all routes from start)
3. `extract-multi --cluster START:END --task …` (clusters before leaves in rewrite order)
4. On XSIAM, verify parent call nodes show bound sub-playbooks (UUID `playbookid`, not name-only)
5. If end’s outside links are missing after leaf extracts, confirm `retarget_all_successors` ran (combined rewrite bug class)

### Delete created copies

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  delete --name-prefix '[REFACTOR' --force
```

Prefix match is **case-sensitive**. `[REFACTOR-M] …` parent copies are deleted before `[REFACTOR-S] …` subs (legacy `[REFACTOR-S-LEAF]`, `[REFACTOR-S-INT]`, `[REFACTOR-SUBPLAYBOOK]`, and parent `[REFACTOR]` also recognized).

### Changing this toolkit

1. Code + tests
2. Update `README.md` and **this** `AGENTS.md` in the same change
3. If the agent entry path or purpose changes, update `ai/guidance-cache/playbook-utils.md` (stub only)

---

## Related docs

| Resource | Role |
| --- | --- |
| [`README.md`](README.md) | Human overview |
| `ai/guidance-cache/playbook-utils.md` | Stub in the AI workspace cache |
| `ai/AGENTS.md` | Workspace agent index (points at the stub) |
| `ai/guidance-cache/xsoar--playbooks.md` | Playbook product/dev conventions |
| `ai/tools/playbook_yaml/README.md` | Offline YAML analysis (exported files, not live API) |
| `bay/scratch/sample-load-and-reupload-playbook.py` | XSOAR 6 YAML save quirks (do not remap ids) |
