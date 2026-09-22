# Playbook utils

**Canonical location:** `cortex-ps-toolkit/playbook-utils/` (toolkit repo root). `bay/playbook-utils` symlinks here for backward-compatible paths.

Utilities for live XSOAR 6, XSOAR 8, and XSIAM playbooks: **inspect**, **analyze** (search inputs/outputs, full-text, branch tracing), **extract**/factor subgraphs, **update** task settings, **upload** YAML exports, copy **lists** between tenants, and cache tenant playbooks via the Core API.

**Analysis** walks a root playbook and all reachable sub-playbooks in the tenant cache (`search-task-inputs`, `search-task-outputs`, `search-tasks`, `show-task`, `trace-branches`). Search and branch-trace commands default to **agent** output — compact `task_summary` blocks instead of full task JSON.

**Extract** factors tasks into new sub-playbooks and uploads a **copy** of the parent. Supports **leaf extract**, **cluster extract** (`--cluster START:END`), and **combined** runs (`extract-multi`).

**Task updates** (`update-playbook-tasks`) overwrite an existing playbook in place for retry/error-handling and sub-playbook context sharing.

Extract uploads a **copy** of the parent; the original playbook is not overwritten.

**Exception:** `update-playbook-tasks` (alias `update-error-retry`) overwrites an existing playbook in place (same id, task ids preserved).

**Agents:** start at [`AGENTS.md`](AGENTS.md) (indexed command map, inspect/assert, extract pipeline).

## Setup

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils
python3 -m pip install -r requirements.txt
python3 -m pip install pytest
```

Credentials file (same shape as `bay/sample-credentials.json`):

```json
{
    "url": "https://api-tenant.xdr.region.paloaltonetworks.com",
    "id": 123,
    "key": "apikey"
}
```

Pass `--tenant-type xsoar6|xsoar8|xsiam` (or `"tenant_type"` in the credentials file). Detection if omitted: `crtx.` → XSOAR 8, `.xdr.` → XSIAM, otherwise XSOAR 6.

| Tenant | List all | Get one | Save | Delete |
| --- | --- | --- | --- | --- |
| XSOAR 6 | `POST /playbook/search` | `GET /playbook/{id}` (search fallback) | `POST /playbook/save/yaml` | `POST /playbook/delete` |
| XSOAR 8 | `POST /xsoar/public/v1/playbook/search` | `GET /xsoar/public/v1/playbook/{id}` | `POST /xsoar/public/v1/playbook/save/yaml` | `POST /xsoar/playbook/delete` (not under `/public/v1`) |
| XSIAM | `POST /xsoar/public/v1/playbook/search` (XSOAR-compat) | `POST /public_api/v1/playbooks/get` (YAML ZIP) | `POST /public_api/v1/playbooks/insert` (YAML ZIP) | `POST /public_api/v1/playbooks/delete` |

## Checks

**(A) Potential root (leaf extract).** A task may be extracted only if:

- it cannot reach itself through `nextTasks` (descendant cycles are allowed)
- no task *outside* the descendant set points at a descendant other than the selected task

**(C) Cluster extract.** A start/end pair (`--cluster START:END`) may be extracted only if:

- end is reachable from start
- end is **not** a conditional task (`type: condition`) — sub-playbook call nodes cannot express conditional branch labels the same way
- no task reachable from start without passing through end (no bypass paths)
- no outside incoming edges to cluster tasks other than start
- no outside outgoing edges from cluster tasks other than end (end’s successors become the sub-playbook call node’s `nextTasks` in the parent)
- cluster tasks do not overlap with any leaf extract in the same run

**(B) Canonical compare.** `extract` diffs the original subgraph (tasks and connections) against the re-downloaded sub-playbook (`compare_source_to_downloaded_subplaybook`). Ids / views / timestamps are ignored by the policy compare (upload gate). A second all-fields dump (`08b-compare-all-fields.txt`) lists every remaining payload difference with no ignore list. The downloaded sub-playbook’s synthetic `start` task is skipped. A `scriptId` present in the source and missing after save is a real mismatch (the UI will show a regular task with no script).

## Cache

Each tenant cache is `.cache/<host-url>/<tenant-type>/` so multiple hosts can be used at once. Populate it with `cache-refresh` (XSOAR 6/8 search, or XSIAM XSOAR-compat `POST /xsoar/public/v1/playbook/search`). After extract, XSIAM reloads the new sub-playbook from that search JSON (not YAML ZIP) so compare is JSON vs JSON. One-off `get --playbook` is still YAML ZIP. TTL default 1 hour. Any upload or delete invalidates that tenant cache. `cache-refresh` writes `manifest.json` / `manifest.txt` into the cache dir and `.debug/`.

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  cache-refresh
```

## Inspect

`inspect` lists task **titles**, **total successors** (reachable descendants excluding the task itself), and whether each task is a **potential root**. Use `--check` to assert those facts (exit 2 on mismatch).

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  inspect --playbook Test_PB_Inv_Data_Main \
  --check '7,name=Print Key_In_Main,successors=2,root=yes' \
  --check '2,name=YES!,successors=3,root=yes' \
  --check '4,name=Test_PB_Inv_Data_Unexpanded_Sub,successors=1,root=no'
```

`--task ID` limits the table. Omit it to list every task. `check-root` remains available for a single potential-root verdict. `extract --task` accepts a task id or a unique task name.

## Playbook analysis

These commands walk a **root playbook and all reachable sub-playbooks** resolved from the tenant cache (`playbook_tree.walk_playbook_tree`). Each match reports:

- **Task id** (tasks-map key in the containing playbook)
- **Task name** and **type**
- **Nesting path** — `Root > Sub A > Sub B`

Run `cache-refresh` first so sub-playbooks resolve. Unresolved sub-playbook references are listed at the bottom of the text report (those branches are skipped).

| Command | Searches | Typical use |
| --- | --- | --- |
| `search-task-inputs` | Task **inputs** — `scriptArguments`, `arguments`, `conditions`, `message`, `form`, `loop`, `timerTriggers`, `fieldMapping` | Find where a context path or field name is **read** (e.g. `${issue.name}` in email bodies) |
| `search-task-outputs` | Task **outputs** — `scriptArguments` / `arguments` keys and values, `fieldMapping` | Find where incident/context fields are **written** (e.g. `setIssue` / `setParentIncidentFields` args) |
| `search-tasks` | Full-text match + compact **`task_summary`** per hit | Find tasks by branch label, script name, field name, etc. |
| `show-task` | One or more tasks by **`--task`** or **`--name-contains`** | Review a known task without dumping full JSON |
| `trace-branches` | Condition branches + upstream **drivers** with assignment `task_summary` | See what sets each branch variable before task 335 runs |

Common flags: `--playbook NAME_OR_ID`, `--force` (bypass cache TTL). Search: `--contains NEEDLE`; optional `--name-contains` (filter by task name). Output search: optional `--script COMMAND`. Branch trace / search: **`--format agent`** (default) or **`--format table`**.

**Exit codes:** `0` when matches / analysis succeeds; **`1`** when a search finds no matches. **`2`** for inspect/assert failures.

**Output:** Agent-format text on stdout (compact summaries); JSON under `.debug/<timestamp>-<command>-…/` includes `task_summary` objects for programmatic review. Add global **`--print-json`** to emit JSON on stdout.

### `task_summary` (JSON)

Each match / shown task / branch driver may include:

| Field | Content |
| --- | --- |
| `name`, `type` | Task title and type (`condition`, `regular`, `playbook`, …) |
| `script` | Command binding when present |
| `playbook_ref` | Sub-playbook id/name for call nodes |
| `successors` | `nextTasks` map (branch label → task ids) |
| `branches` | Condition tasks only — label, condition text, variables, successors |
| `arguments` | Simplified inputs (`set_key` / `set_value` for `Set`, or field→value) |

### `trace-branches` drivers

For each branch label, the report lists the **driver** task that sets the branch variable (e.g. `Set ResultCondition` in a CheckList sub-playbook). If none is found upstream, the branch shows **`start_fallback`** (no assignment in the playbook tree).

### Examples (BAY XSIAM phishing playbooks)

Find input references to issue name:

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  search-task-inputs \
  --playbook '[Splunk] Phishing Email Reported by User' \
  --contains 'issue.name'
```

Find `setIssue` tasks that write a field containing `name`:

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  search-task-outputs \
  --playbook '[Splunk] Phishing Email Reported by User' \
  --contains name \
  --script setIssue
```

Find and review task 335 (condition branching):

```bash
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

Scan whether incident fields are read or only written (performance / dead-code review):

```bash
for field in krungsricategory ncsacategory ncsaasset; do
  python3 -m playbook_utils \
    --credentials ../bay-credentials-2.json \
    --tenant-type xsiam \
    search-tasks \
    --playbook '[Splunk] Phishing Email Reported by User' \
    --contains "$field"
done
```

`trace-branches` resolves variables like `ResultCondition`, `incident.eventid`, and `issue.name` against upstream `Set`, `setIssue`, and sub-playbook tasks. When no assignment is found, it reports a **`start_fallback`** on the root playbook start task (meaning the branch value is never set in the tree — likely dead code or set outside the playbook).

For **offline exported YAML** (fixed local sub-playbook files, no live cache), use `ai/tools/playbook_yaml/` instead.

## Extract

**Single leaf extract:**

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  extract --playbook 'Playbook Name' --task 12
```

**Combined leaf + cluster extract** (one parent copy):

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  extract-multi --playbook '[Splunk] Phishing Email Reported by User' \
  --cluster 21:52 \
  --task 366 --task 368 --task 370 --task 454 --task 372 --task 373
```

- `--task` — repeatable; each must be a potential root (leaf extract).
- `--cluster START:END` — repeatable; `START` and `END` may be task ids or unique task names.
- Cluster extractions run first on the parent copy, then leaf extractions. When a later leaf extract removes a task that the cluster call still points at, **all** `nextTasks` references to that task id are retargeted to the new sub-playbook call node.

A **damp run** uploads, re-downloads, compares, then deletes the created playbooks:

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  extract --playbook 'Playbook Name' --task 12 --damp-run
```

**Batch upload + validate** (upload subs/parent without per-item compare, then one cache refresh and compare):

```bash
python3 -m playbook_utils extract-multi ... --upload-only
python3 -m playbook_utils validate-jobs --jobs .debug/.../00-result.json
```

Default names (override leaf sub name on single `extract` with `--sub-playbook-name`; override parent with `--parent-copy-name`):

| Artifact | Pattern |
| --- | --- |
| Leaf sub-playbook | `[REFACTOR-S] {main} [LEAF from {task_id}]` |
| Cluster sub-playbook | `[REFACTOR-S] {main} [INT from {start_id} to {end_id}]` |
| Parent copy | `[REFACTOR-M] {main} [at {ts}]` — `{ts}` is UTC ISO to minute precision (no seconds), e.g. `2026-09-09T19:14+00:00` |

The extracted sub-playbook is uploaded with playbook-level `separatecontext: true`. The new parent call node uses `separateContext: false` so the sub-playbook shares the incident context. YAML key spellings, bindings, and drop/ignore lists: [YAML upload field mapping](#yaml-upload-field-mapping). Parent copy is uploaded only if compare matches (unless `--upload-parent-on-mismatch`).

### Refactor descriptions

On a successful extract, playbook-level **descriptions** are written to each generated sub and the parent copy (not inner task descriptions). See [`AGENTS.md` § Refactor descriptions](AGENTS.md#refactor-descriptions) for full format.

**Parent `[REFACTOR-M]`** — preserves any existing source description, then documents each cluster/leaf extraction, optional HttpV2 retry summary (with sub-playbook names on the task sub-list), and **totals-only** refactor metrics:

```text
Refactor Metrics:
 - 81 nodes moved
 - 7 call nodes added
 - 11 incoming links re-written
 - 3 outgoing links re-written
```

**Sub `[REFACTOR-S]`** — `Refactored from …`, one aspect line, optional HttpV2 block (task numbers only).

**Debug files** (step 12): `12-parent-description.txt`, `12-sub-description-NN.txt`, `12-refactor-metrics.txt` (full per-sub metrics + totals — not uploaded).

Combine with post-task HttpV2 tuning in one run:

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials.json \
  extract-multi --playbook '[Splunk] Phishing Email Reported by User' \
  --cluster 21:52 \
  --task 366 --task 368 --task 370 --task 372 --task 373 --task 454 \
  --post-task-update 'contains:HttpV2:i|retry=30x30,stop-on-error'
```

On **XSIAM**, sub-playbook call bindings in uploaded YAML use tenant `playbookid` (UUID) rather than `playbookName`. After sub upload, the toolkit resolves each sub’s assigned id from cache before building the parent copy.

Useful flags:

| Flag | Effect |
| --- | --- |
| `--damp-run` | Upload and compare, then delete the created playbooks |
| `--require-match` | Exit 2 on round-trip mismatch |
| `--upload-parent-on-mismatch` | Still upload the parent copy |
| `--skip-parent` | Only create the sub-playbook |
| `--post-task-update MATCH\|actions` | After sub compare, apply task updates on generated subs before descriptions + parent upload (`extract-multi` only; repeatable) |
| `--fields-config policy.json` | Override ignore/drop field lists |
| `--debug-dir PATH` | Where to write artifacts (default `.debug/<timestamp>-...`) |
| `--cache-ttl 0` | Cache until the next invalidate |
| `--insecure` | Skip TLS verify (XSOAR 6 lab IPs) |

Every `get` / `inspect` / `check-root` / `compare` / `extract` / `extract-multi` / `validate-jobs` / `delete` run writes JSON + text under `--debug-dir` so mismatches can be diffed (canonical graphs, upload YAML, download JSON, field policy). The parent copy removes extracted tasks and inserts sub-playbook call nodes at the original start/leaf positions.

Delete created copies (case-sensitive name prefix; parent `[REFACTOR-M]` before subs `[REFACTOR-S] …`):

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  delete --name-prefix '[REFACTOR' --force
```

## Update playbook tasks (`update-playbook-tasks`)

Overwrite an existing playbook in place. Two update types, each with **task-type checks**:

| Update type | Flag | Valid task type |
| --- | --- | --- |
| On Error retry / error handling | `--update TASK:actions` | `regular` with a script binding (`scriptId` / `scriptName` / `script`) |
| Context sharing | `--context-update TASK:sharing` | `playbook` (sub-playbook call with `playbookName` / `playbookId`) |

Invalid tasks are **rejected before upload** (listed in the report); valid updates in the same command are still applied. Exit **2** when any task is rejected or post-upload validation fails.

Playbook id, task ids, and inner task UUIDs are preserved (`prepare_for_overwrite`).

### On Error retry (regular script tasks)

| UI field | API / YAML location |
| --- | --- |
| Number of retries | `scriptArguments.retry-count.simple` |
| Retry interval (seconds) | `scriptArguments.retry-interval.simple` |
| Stop on error | `continueOnErrorType: ""`, no `continueOnError` |
| Continue | `continueOnError: true`, `continueOnErrorType: ""` |
| Continue on error path | `continueOnError: true`, `continueOnErrorType: errorPath`, `#error#` in `nextTasks` |

Collection tasks use `message.timings.retriesCount` / `retriesInterval` instead — not handled by this command yet.

### Context sharing (sub-playbook call tasks)

| UI / intent | API / YAML |
| --- | --- |
| Global / shared incident context | `separateContext: false` (`separatecontext: false`) |
| Sub-playbook isolated context | `separateContext: true` |

`--context-update` sharing values: `global` (aliases: `share`, `shared`, `incident`) or `subplaybook` (aliases: `isolated`, `separate`).

### Examples (lab `Test_PB_Inv_Data_Main`)

Retry on tasks 4 (playbook — rejected) and 8 (Set script — applied):

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  update-playbook-tasks --playbook Test_PB_Inv_Data_Main \
  --update '4:retry=15x45' \
  --update '8:retry=15x45'
```

Context on tasks 4 (playbook — applied) and 8 (regular — rejected):

```bash
python3 -m playbook_utils \
  --credentials ../lab-xsoar-credentials.json \
  --tenant-type xsoar8 \
  update-playbook-tasks --playbook Test_PB_Inv_Data_Main \
  --context-update '4:global' \
  --context-update '8:global'
```

`--update` actions (repeatable):

| Action | Meaning |
| --- | --- |
| `clear-retry` | Remove `retry-count` / `retry-interval` from `scriptArguments` |
| `retry=NxI` | Set retry count N and interval I seconds |
| `stop-on-error` | Stop on error |
| `continue` | Continue (leave error path unchanged) |
| `error-path` | Continue on error path |

Omit error-handling actions on a task to leave its handling unchanged. Use `--validate-task` to include extra tasks in the before/after report. `--dry-run` builds upload YAML without calling the API.

`update-error-retry` is a backward-compatible alias for `update-playbook-tasks`.

Match tasks by title when bulk-updating (used with `--match-update`):

| Spec | Meaning |
| --- | --- |
| `PATTERN` | `contains`, case-sensitive |
| `contains:PATTERN` | substring, case-sensitive |
| `contains:PATTERN:i` | substring, case-insensitive |
| `equals:PATTERN` | exact title, case-sensitive |
| `equals:PATTERN:i` | exact title, case-insensitive |

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  update-playbook-tasks --name-prefix '[REFACTOR-S]' \
  --match-task-name 'contains:HttpV2:i' \
  --match-update 'retry=30x45,stop-on-error'
```

## Upload YAML exports

Upload exported playbook or script YAML from disk (does not remap script/playbook id **values** across tenants).

| Command | XSOAR 6 | XSOAR 8 | XSIAM |
| --- | --- | --- | --- |
| `upload-playbooks PATH…` | `POST /playbook/save/yaml` | `POST /xsoar/public/v1/playbook/save/yaml` | `POST /public_api/v1/playbooks/insert` (YAML ZIP) |
| `upload-scripts PATH…` | `POST /automation/import` | `POST /xsoar/public/v1/automation` | `POST /public_api/v1/scripts/insert` (YAML ZIP) |

```bash
python3 -m playbook_utils \
  --credentials ../mfec-uat-credentials.json \
  --tenant-type xsiam \
  upload-playbooks ../phishing-playbook/assets/playbooks --recursive

python3 -m playbook_utils \
  --credentials ../mfec-uat-credentials.json \
  --tenant-type xsiam \
  upload-scripts ../phishing-playbook/assets/custom-scripts --recursive
```

Pass one or more files or directories. Use `--recursive` to include nested `.yml` / `.yaml` files. Outcomes are written to `.debug/…/01-upload-outcomes.{json,txt}`. Any upload invalidates that tenant's cache.

## Lists (XSOAR 8 / XSIAM)

| Command | Purpose |
| --- | --- |
| `list-lists` | List tenant lists (`GET /xsoar/public/v1/lists`); optional `--name-contains` |
| `copy-list` | Copy list(s) from one tenant to another via `lists/save` |

```bash
python3 -m playbook_utils \
  --credentials ../bay-credentials-2.json \
  --tenant-type xsiam \
  list-lists --name-contains IssueCategory

python3 -m playbook_utils copy-list \
  --from-credentials ../bay-credentials-2.json \
  --to-credentials ../mfec-uat-credentials.json \
  --from-tenant-type xsiam --to-tenant-type xsiam \
  IssueCategory
```

`copy-list` supports `--target-name` (single list), `--target-prefix`, `--no-overwrite`, and `--commit-message`.

## YAML upload field mapping

GET/search returns **camelCase API JSON**. `/playbook/save/yaml` keeps **lowercase schema keys** except `scriptName`, `playbookName`, `exitCondition`, `fieldMapping`, `inputSections`, and `vcShouldKeepItemLegacyProdMachine`. Playbook input/argument names (`assignBy`, `GetOriginalEmail`) are not rewritten.

### Structure

A saved playbook is `id` / `name` / `version: -1` / `starttaskid` / `tasks`. Each task has:

- `id`, `type`
- inner `task` (`name`, `type`, `brand`, `iscommand`, `version: -1`, plus a **binding** — see below)
- `nexttasks` (branch label → task ids)
- optional `scriptarguments`, `conditions`, `loop`, `timertriggers`, `message`, `form`, `view` (JSON string)

### Bindings (API JSON → YAML)

| API field | YAML field | Notes |
| --- | --- | --- |
| `scriptId` (automation) | `scriptName` | Delete `scriptId`. Save ignores `scriptid` and the UI shows no script. |
| `scriptId` when `isCommand` or `Brand\|\|\|command` | `script` | `iscommand: true` |
| `playbookId` | `playbookName` (XSOAR) or `playbookid` (XSIAM when id known) | XSOAR: delete `playbookId`. XSIAM parent/subs: keep UUID binding |
| `fieldMapping[].fieldId` | `fieldMapping[].incidentfield` | Keep `fieldMapping` camelCase. `fieldmapping` / `fieldId` are ignored on save. |

### Nested schema that must be lowercase

| API JSON | YAML |
| --- | --- |
| `timerTriggers[].fieldName` | `timertriggers[].fieldname` (`action` is `start` / `stop`) |
| `form.questions[].labelArg` / `optionsArg` | `labelarg` / `optionsarg` |
| `message.timings.retriesCount` / `retriesInterval` / `completeAfterReplies` / `completeAfterV2` / `completeAfterSla` | `retriescount` / `retriesinterval` / `completeafterreplies` / `completeafterv2` / `completeaftersla` |
| `nextTasks`, `scriptArguments`, `separateContext`, `continueOnErrorType`, `isCommand`, `isContext`, `ignoreCase`, `readOnly` | all-lowercase |
| `fieldMapping` | **`fieldMapping` (preserve camelCase)** — `fieldmapping` is ignored on save |

Other schema aliases (`starttaskid`, `reputationcalc`, `defaultassigneecomplex`, …) live in `playbook_utils/keys.py` (`_ALIASES`). Full table: [`AGENTS.md`](AGENTS.md#yaml-upload-field-mapping).

### Dropped vs ignored

Upload **drops** server-owned metadata (`modified`, `sequenceNumber`, `primaryTerm`, inner `task.id`, node `taskId`, pack fields, …). `primaryTerm` is an Elasticsearch index generation counter, not playbook logic.

Policy compare (whether the parent copy is uploaded) **ignores** those plus `id`, `view`, `version`. It does **not** ignore script bindings, timers, form labels, or graph edges. `extract` also writes `08b-compare-all-fields.txt` with nothing ignored.

To find a new YAML spelling from a tenant export:

```bash
python3 -m playbook_utils discover-yaml-keys \
  --yaml examples/Phishing_-_Generic_v3_copy.yml \
  --json path/to/api-playbook.json \
  --task 39
```

## Tests

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit/playbook-utils
python3 -m pytest -q
```

When you change behaviour or CLI flags, update this README and `AGENTS.md` together.

Existing playbooks uploaded before the `scriptName` YAML fix need a fresh extract; they were saved without script bindings.
