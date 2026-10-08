# Feature specifications

Behavioural specs for Cortex PS Toolkit features. Implementation targets Python first; the **dev server** exposes the same capabilities to the web UI.

**UI shell:** icon navigation rail (titles on hover) — see [`UI_AND_SERVER.md`](UI_AND_SERVER.md).

| Section | Primary actions |
| --- | --- |
| API Profiles | CRUD + validate profiles |
| XQL Query Tool | Run queries, history by ID, reload results + charts |
| Playbook Tools | Navigate cache, **refresh playbooks+scripts**, refactor, copy playbooks, copy component subs+scripts |
| Script Tools | Navigate cache, refresh scripts, copy scripts to other tenant |
| Bundles | Basket + saved presets, catalog tabs (incl. **custom integration definitions**), cross-tenant copy (integrations → scripts → playbooks → lists → design), portable ZIP export, playbook dependency scan, deep-copy-style result UI — see [`BUNDLES.md`](BUNDLES.md) |

---

## 1. Credentials manager

### User stories

- Operator registers one or more tenant profiles without editing JSON by hand (CLI or web form)
- Operator selects active profile for all subsequent commands
- Toolkit validates connectivity and detected platform before long cache refreshes

### Acceptance criteria

- [ ] CRUD on `data/collections/credentials.json` (see [`STORAGE.md`](STORAGE.md))
- [ ] List shows label, url, tenant_type, api_id (masked key)
- [ ] `validate` succeeds against live tenant with clear error on auth failure
- [ ] No credential material in logs, debug JSON, or git

---

## 2. Content cache

### User stories

- Operator refreshes playbook catalog once, then works offline-ish for analysis
- Two profiles pointing at same URL with different API keys maintain separate caches
- Operator sees cache age, object counts, and stale scopes

### Refresh scope rules

| Trigger | Scopes |
| --- | --- |
| **Playbook Tools → Refresh cache** | `playbooks` **and** `scripts` (single action) |
| **Script Tools → Refresh cache** | `scripts` only |
| CLI | `--scope playbooks`, `scripts`, `playbooks+scripts`, or `all` |

### Acceptance criteria

- [ ] Cache path includes `host / tenant_type / api_id`
- [ ] Playbook Tools refresh always updates both playbooks and scripts indexes
- [ ] `meta.json` + `index.json` written on successful refresh
- [ ] TTL respected; `--force` bypasses freshness check
- [ ] Upload/delete through toolkit invalidates relevant scope

---

## 3. XQL query tool

Port and extend [`bay/utilities/xql-query-monitor.html`](../../bay/utilities/xql-query-monitor.html).

### API flow

Per [Cortex XQL Query API](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/xql-query):

1. `POST /public_api/v1/xql/start_xql_query` — `query`, `timeframe`
2. `POST /public_api/v1/xql/get_query_results` — poll until not `PENDING`
3. `POST /public_api/v1/xql/get_query_results_stream` — JSONL when `stream_id` present

XSOAR tenants may use different base paths — route via `core/client.py` platform table.

### Presets

| Tier | Storage | Operations |
| --- | --- | --- |
| Application | `presets/xql/application/` | Shipped; versioned with toolkit |
| Server | `data/presets/xql/<profile>/` | CRUD via CLI/web; per credential profile |
| Import/export | TSV / JSONL files | Offline replay (no live API) |

**Built-in application presets** (from XQL monitor):

| Preset | Dataset | Purpose |
| --- | --- | --- |
| Case Resolution | `cases` | Resolved cases, duration, status |
| Issue Resolution | `issues` | Issue timer resolution stats |
| Playbook Run Performance | `playbook_runs` | Aggregated run duration / failure rate by playbook |
| Playbook Task Performance | `playbook_tasks` | Task duration, retry, error rate by task |
| Playbook Task Errors | `playbook_tasks` | Row-level error events |

### Results handling

- Normalise column names (dots in field names preserved in export)
- Timestamp inference (name hints + value sampling) — same rules as HTML monitor README
- Export: TSV, JSONL, optional inline preview (first N rows)
- Query metrics when API returns them (row count, cost, quota, status)

### Visualisations

**Preset quick charts:** rule engine in the XQL monitor inspects result schema + optional preset hint → fixed Plotly charts (“Generate: …”).

**Custom visual builder:** chart type + column→encoding map, validate/render via `/api/xql/visualizations/*` (see [`xql-visual-builder.md`](xql-visual-builder.md)). XQL must return aggregated rows; no summing in the chart layer.

| Visualisation group | Trigger schema | Charts |
| --- | --- | --- |
| Case / Issue Duration | `duration`, `create_time`, `resolution_time`, issue id | Histogram (resolved), scatter by status, **Time in System** step line (active count), hourly volume |
| Playbook Run Performance | aggregated playbook columns | Avg/median duration (separate charts), failure rate, failed count |
| Playbook Task Performance | `task_id`, `task_name`, duration stats | Avg/median by task composite key, error rate/count |
| Playbook Task Errors | row-level errors + `_time` | Count by task/script, hourly stacked bars |

CLI example (planned):

```bash
python -m cortex_ps_toolkit xql run --profile bay-xsiam-prod \
  --preset playbook-run-performance --timeframe 7d \
  --output results.jsonl --suggest-charts
```

Web UI renders suggested charts; CLI prints chart types and optional static HTML export.

### Query history

Each run (or explicit save) gets a stable **query ID** stored in `data/collections/xql_queries.json`.

| Capability | Behaviour |
| --- | --- |
| History list | ID, label, ran_at, row count, status |
| Hover ID | Tooltip/popover with **full query text**, timeframe, profile |
| Load | Hydrate grid + visualisations from stored `xql_results/{id}.jsonl` without re-running API |
| Re-run | Optional action to execute same query again (new ID) |
| Pin | Pinned entries exempt from cleanup retention |

### Acceptance criteria

- [ ] Live run using stored credential profile
- [ ] All five application presets runnable
- [ ] Server preset CRUD
- [ ] TSV/JSONL import without API (offline mode)
- [ ] Schema detection matches HTML monitor behaviour for shared test fixtures
- [ ] Suggested visualisations for each built-in preset
- [ ] Query history with ID; hover shows full query; load restores results and charts

---

## 4. Playbook tools (navigate, metrics, copy, refactor)

### 4a. Navigate and refresh cache

- Playbook list/table from cache index (search, sort, filter by tag/name)
- Select playbook → exploded metrics tree (main + reachable subs)
- **Refresh cache** updates **playbooks and scripts** for active profile

### 4b. Copy operations

| Action | Behaviour |
| --- | --- |
| **Copy selected playbooks** | Upload YAML for selected playbook(s) to a **target credential profile** (cross-tenant copy) |
| **Copy component sub-playbooks and scripts** | From selected root(s): walk sub-playbook refs + collect automation scripts used; copy entire dependency set to target tenant |

Preflight: resolve names/ids on target; report conflicts; optional dry-run manifest.

### 4c. Refactor playbooks

See §5 below (same capability, launched from Playbook Tools toolbar).

**Read path (validate, preview, update-tasks preview):** playbook JSON comes only from toolkit cache (`playbooks/bodies/` + index). Missing bodies → 404 with refresh guidance; no playbook-utils bulk search.

**Execute:** seeds an isolated playbook-utils job cache from toolkit bodies, then runs `extract-multi` (tenant uploads/compare only).

---

## 5. Playbook listing and exploded metrics (detail)

### User stories

- Operator browses playbook inventory from cache (fast, no live search per click)
- Operator opens a root playbook and sees **recursive** structure: main + all reachable sub-playbooks
- Operator views automation metrics (task type breakdown, script commands, automation ratio)

### Data sources

- Playbook **index** and **bodies** under `data/cache/.../playbooks/` (see [`CHANGELOG-post-initial-commit.md`](CHANGELOG-post-initial-commit.md))
- Metrics library: [`ai/scripts/xsoar_playbook_metrics.py`](../../ai/scripts/xsoar_playbook_metrics.py)
- Tree walk pattern: [`playbook-utils/playbook_utils/playbook_tree.py`](../../playbook-utils/playbook_utils/playbook_tree.py)

### Exploded view model

```
Root: [Splunk] Phishing Email Reported by User
├── metrics: 147 tasks, 62% automated, 12 sub-playbook calls
├── Sub: Enrichment PB (id …)
│   └── metrics: 23 tasks, …
└── Sub: Close Incident (id …)
    └── metrics: 8 tasks, …
Combined workflow metrics: reachable automated / total across tree
```

### UI / CLI outputs

| Output | Content |
| --- | --- |
| List table | name, id, task count, modified, tags, pack |
| Detail | structure tree, per-playbook tabulation, script/command frequency |
| Compare | optional diff two cached versions (future) |

### Acceptance criteria

- [ ] List from index without N+1 API calls
- [ ] Recursive expansion resolves subs by id/name from same cache
- [ ] Metrics match offline script output for fixture playbooks
- [ ] Unresolved sub-playbook refs reported explicitly (not silent skip)

---

## 6. Playbook refactoring

Port behaviour from [`playbook-utils`](../../playbook-utils/) — see its AGENTS.md § Extract pipeline and § Refactor descriptions.

### Capabilities

| Operation | Description |
| --- | --- |
| Leaf extract | Single potential-root task + descendants → sub-playbook |
| Cluster extract | Start→end segment including side branches |
| Combined | Multiple clusters + leaves → one `[REFACTOR-M]` parent copy |
| Compare (B) | Canonical subgraph round-trip before parent upload |
| Post-task update | HttpV2 retry/error-handling on generated subs |
| Descriptions | Playbook-level parent + sub descriptions; full metrics in debug log |

### Naming conventions (unchanged)

| Artifact | Pattern |
| --- | --- |
| Leaf sub | `[REFACTOR-S] {main} [LEAF from {task_id}]` |
| Cluster sub | `[REFACTOR-S] {main} [INT from {start} to {end}]` |
| Parent copy | `[REFACTOR-M] {main} [at {timestamp}]` |

### Toolkit integration

- Invoked via CLI: `playbooks extract-multi --profile X --playbook '...' --cluster ... --task ...`
- Web UI: form for task ids + dry-run / upload-only / damp-run flags
- Uses active credential profile cache; refresh before refactor if stale
- Debug output under `.debug/` (compare reports, descriptions, metrics log)

### Acceptance criteria

- [x] Parity with playbook-utils extract-multi (validated on MFEC UAT Splunk/SIM presets; BAY prompts are reference scenarios only)
- [ ] Descriptions: totals-only metrics on parent; full metrics in `12-refactor-metrics.txt`
- [ ] Original playbook never overwritten
- [ ] XSIAM sub-playbook binding by `playbookid`

---

## 7. Script tools

Dedicated nav section for automation scripts (subset of content management focused on scripts).

| Action | Behaviour |
| --- | --- |
| **Navigate / refresh cache** | Script list from cache; refresh **scripts scope only** |
| **Copy selected scripts** | Upload selected scripts to target credential profile |

Playbook Tools refresh remains the primary path when preparing for playbook work (always refreshes scripts too).

### Acceptance criteria

- [ ] Script list from `index.json` scripts array
- [ ] Copy to target tenant with outcome report per script
- [ ] Refresh scripts without full playbook pull

---

## 8. Bundles (extended workflow)

Full spec: [`BUNDLES.md`](BUNDLES.md). REST: [`api/toolkit/bundles.md`](api/toolkit/bundles.md).

### User stories

- Operator assembles integrations, lists, scripts, playbooks, and object-setup assets into one basket without switching nav sections repeatedly.
- Operator saves/loads named presets per source tenant.
- Operator copies the basket to a target tenant in safe dependency order with one confirm dialog (operation plan).
- Operator exports a portable ZIP for offline transfer (XSOAR 6 manual import).
- Operator scans playbook dependencies and adds missing scripts/subs to the basket.

### Copy result UX

After execute, the Bundles panel shows the same **copy result shell** as deep copy:

- Collapsible **alerts** (failures, binding warnings, post-copy diff warnings).
- **Summary** lines per phase (success counts align with toast via `copy_entry_succeeded`, including HTTP 2xx design rows).
- **Full response (JSON)**.
- **View classified copy diffs** when `post_copy_diff` was enabled (nested phase rows + optional top-level merged report).

### Post-copy diff scope

| Phase | `post_copy_diff` |
| --- | --- |
| Scripts, playbooks (shallow), lists | Yes |
| Integrations | Yes (portable definition document) |
| Design assets (object setup) | Yes |
| Correlation rules (object setup / bundle orchestrator) | Yes |

### Acceptance criteria

- [x] Multi-phase copy plan + execute with integrations in basket
- [x] Portable ZIP export with integration/script/playbook shaping
- [x] Bundle result UI (alerts, summary, diff panel, JSON)
- [x] Nested copy notification flattening for summary toast
- [x] Web UI uses WebSocket `bundles.copy` with live progress when WS connected (HTTP fallback)
- [x] Post-copy diff on design-phase assets (via bundle orchestrator when **Diff after copy** enabled)
- [x] Catalog “hide already in basket” filter
- [x] CLI `bundles` subcommands (copy, export, resolve)
- [x] Operation-plan confirm for integrations and object-setup copy (via `normalizeConfirmPlan`)

---

## 9. Content management (develop as Python utilities first)

Manage design-time content objects beyond playbooks. Each type follows the same pattern:

1. **List** — from cache index or live search
2. **Get** — full object JSON/YAML
3. **Cache refresh** — scope-specific pull
4. **Compare** (optional) — export vs cached snapshot
5. **Upload** (optional, later) — YAML insert/save with validation

### 9.1 Scripts (automations)

| API (typical) | XSOAR 8 / XSIAM |
| --- | --- |
| Search / list | `POST .../automation/search` or tenant equivalent |
| Get | By id or name |
| Upload | `save/yaml` or `scripts/insert` (XSIAM ZIP) |

**Utilities:** list by prefix, show script args/outputs, find scripts referencing command, export YAML bundle.

### 9.2 Integrations

Integration **definitions** (pack content): list, get, show command list, docker image, dependences.

Reference: demisto content structure + [`ai/guidance-cache/xsoar--integrations-and-scripts.md`](../../ai/guidance-cache/xsoar--integrations-and-scripts.md).

### 9.3 Integration instances

Configured instances on tenant: list, get config (secrets masked in UI), test connectivity hook, compare config snapshots.

**Security:** mask password/API fields in logs and web display; optional separate “secrets reveal” for local admin.

### 9.4 Correlation rules (XSIAM)

XSIAM-specific content. List/get rules from tenant API; cache under `correlation_rules/`.

Use cases: inventory for tuning engagements, export rule XQL/query text, diff against prior cache.

**Research needed during implementation:** exact public API paths per tenant version — consult `tools.cortex_docs search "correlation rule"` from `ai/`.

### 9.5 Widgets

Dashboard/report widgets: list, get definition, show data source bindings.

Tied to XSOAR reports/dashboards APIs where available.

### Shared CLI pattern (planned)

```bash
python -m cortex_ps_toolkit content list scripts --profile X [--prefix foo]
python -m cortex_ps_toolkit content get integration --profile X --name "Slack v3"
python -m cortex_ps_toolkit content refresh --profile X --scope correlation_rules
```

### Acceptance criteria (phase 2 content)

- [ ] Each content type: list + get + cache refresh
- [ ] Index entries in `index.json` under type-specific keys
- [ ] Masked secrets for integration instances
- [ ] Unit tests with fixture JSON per type

---

## Cross-cutting concerns

### Copy / diff presentation (web)

Shared modules: `web/static/copy-result-ui.js`, `web/static/copy-diff-panel-ui.js`, `web/static/operation-ui.js` (copy mode controls).

| Surface | Result shell |
| --- | --- |
| List / script / playbook bulk copy | `presentCopyResultView` + outcome dialog |
| Playbook deep (component) copy | `presentDeepCopyResultView` + summary |
| **Bundles copy** | `presentBundleCopyResultView` + `summarizeBundleCopyResult` |
| Integrations copy | Bulk alerts + outcome dialog |

**Post-copy diff:** optional on execute; classified **flagged** vs **ignored** deltas in modal panel (`repr-copy-fidelity` probe). Documented per resource in `docs/api/toolkit/{lists,scripts,playbooks,bundles}.md`.

| Concern | Approach |
| --- | --- |
| Debug artifacts | `.debug/<timestamp>-<command>/` with JSON + text |
| Exit codes | 0 success, 1 operational error, 2 validation/compare failure (match playbook-utils) |
| Platform detection | URL + explicit `tenant_type`; document overrides |
| Long operations | Progress logging; web SSE or poll for status (later) |
| Disk hygiene | Background cleanup every 15 min ([`STORAGE.md`](STORAGE.md)) |
| Dev experience | `./scripts/dev-server.sh` — debug + Python auto-reload ([`UI_AND_SERVER.md`](UI_AND_SERVER.md)) |
