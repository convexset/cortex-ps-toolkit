# Roadmap

Phased delivery: **Python utilities and CLIs first**, local web application last.

---

## Phase 0 — Documentation ✅ (current)

- Architecture, credentials/cache model, feature specs, prior-art index
- `.gitignore` for secrets and cache
- Agent guide (`AGENTS.md`)

**Exit:** team agrees on scope, cache key design, and module layout.

---

## Phase 1 — Core + credentials + playbook cache

**Goal:** reusable foundation and first vertical slice (playbook list from cache).

| Deliverable | Module |
| --- | --- |
| Package skeleton `cortex_ps_toolkit/` | `pyproject.toml` or `requirements.txt` |
| Credential CRUD + validate | `core/credentials.py` |
| Cache with **api_id-scoped** paths | `core/cache.py` |
| HTTP client (XSOAR 6/8/XSIAM) | `core/client.py` |
| Playbook cache refresh + index | `playbooks/cache.py` |
| CLI: `credentials`, `cache refresh`, `playbooks list` | `cli.py` |

**Reuse:** port/adapt from `bay/playbook-utils` (`credentials.py`, `cache.py`, `client.py`) with cache key change.

**Tests:** offline fixtures; optional live mark against lab tenant.

**Exit:** operator can register a profile, refresh playbooks, list inventory from cache.

---

## Phase 2 — XQL runner + presets

**Goal:** parity with XQL monitor core (without web UI).

| Deliverable | Module |
| --- | --- |
| XQL start/poll/stream | `xql/runner.py` |
| Application presets (5 built-ins) | `presets/xql/application/` |
| Server preset CRUD | `xql/presets.py` + `data/presets/` |
| Timestamp / schema inference | `xql/schema.py` |
| TSV/JSONL import | `xql/import_results.py` |
| Visualization rule engine | `xql/visualizations.py` |
| CLI: `xql run`, `xql import`, `xql presets` | `cli.py` |

**Reuse:** logic and preset text from `bay/utilities/xql-query-monitor.html`; document in `PRIOR_ART.md`.

**Exit:** CLI runs Playbook Run Performance preset, exports TSV, prints suggested chart types.

---

## Phase 3 — Playbook metrics + refactor

**Goal:** exploded metrics view and full refactor pipeline.

| Deliverable | Module |
| --- | --- |
| Playbook tree walk from cache | `playbooks/tree.py` |
| Metrics aggregation | `playbooks/metrics.py` (wrap `ai/scripts/xsoar_playbook_metrics.py`) |
| CLI: `playbooks show`, `playbooks metrics --recursive` | `cli.py` |
| Refactor orchestration | `playbooks/refactor.py` (wrap playbook-utils or editable dep) |
| CLI: `playbooks extract-multi` | `cli.py` |

**Exit:** BAY phishing playbook refactor runnable via `cortex_ps_toolkit` with same outcomes as playbook-utils; metrics tree matches offline analysis.

---

## Phase 4 — Content management utilities

**Goal:** list/get/cache for non-playbook content.

| Order | Type | Rationale |
| --- | --- | --- |
| 4a | Scripts | Smallest API surface; used by playbook metrics |
| 4b | Integrations + instances | Common PS engagement inventory |
| 4c | Correlation rules (XSIAM) | XSIAM-specific; API research required |
| 4d | Widgets | Lower priority; dashboard engagements |

Each type: `content/<type>/cache.py`, `list`, `get`, tests with fixtures.

**Exit:** `content list integrations --profile X` returns cached inventory.

---

## Phase 5 — Local web application

**Goal:** unified UI started by `./scripts/dev-server.sh` (debug + Python auto-reload).

| Deliverable | Notes |
| --- | --- |
| `serve` command + dev script | uvicorn/werkzeug reload; `CORTEX_PS_DEBUG` |
| JSON collections layer | `credentials.json`, `xql_queries.json` ([`STORAGE.md`](STORAGE.md)) |
| Cleanup thread | Every 15 min; retention for XQL results + debug dirs |
| Shell UI + icon nav rail | Credentials, XQL, Playbook Tools, Script Tools ([`UI_AND_SERVER.md`](UI_AND_SERVER.md)) |
| CDN front-end | Tabulator + Plotly; fetch API partial updates |
| XQL history | Query IDs; hover full query; load stored results + charts |
| Playbook Tools | Refresh **playbooks+scripts**; refactor; copy playbooks; copy component subs+scripts |
| Script Tools | Refresh scripts; copy scripts to other tenant |
| Same-origin API proxy | Like `serve-xql-monitor.py` |

**Exit:** operator can complete BAY phishing refactor and XQL monitoring from the browser (CLI still supported).

---

## Phase 6 — Polish (optional)

- Workflow PDF/report export (tie-in to `gic/pdf-report-generation/`)
- Batch jobs manifest (`validate-jobs` pattern)
- Credential profile encryption at rest
- Playbook version diff (cache snapshots over time)

---

## Dependency graph

```
Phase 0 (docs)
    │
    ▼
Phase 1 (core + playbook cache) ─────────────────────────┐
    │                                                     │
    ├──────────────► Phase 2 (XQL)                       │
    │                     │                               │
    └──────────────► Phase 3 (metrics + refactor)        │
                          │                               │
                          ├──────────────► Phase 4 (content)
                          │                     │
                          └──────────────► Phase 5 (web)
```

Phases 2 and 3 can proceed in parallel after Phase 1.

---

## Success metrics (operator engagement)

Primary refactor/copy benchmarks run on **MFEC UAT** (`mfec-uat` presets under `presets/refactor/`). Reference scenarios in [`bay/scratch/bay-prompts.md`](../../bay/scratch/bay-prompts.md) describe equivalent BAY playbooks but are not a required benchmark gate.

1. Refactor Splunk + SIM phishing presets (cluster 21:52 + leaf tasks + HttpV2 30×30) on MFEC UAT
2. XQL Playbook Task Performance / Errors presets over last 7 days
3. Exploded metrics on refactored `[REFACTOR-M]` parent vs original
