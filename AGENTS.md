# Cortex PS Toolkit — Agent Guide

**Start here** when working in `/Users/weichen/Downloads/dev/cortex-ps-toolkit/` (sibling of `bay/`, `ai/`, `gic/` under `dev/`).

Human overview: [`README.md`](README.md).

---

## Purpose

Unified **local** toolkit for Cortex tenant operations during professional-services engagements:

1. Manage tenant **credentials** (server-side files)
2. Maintain **content caches** scoped per credential profile
3. Run **XQL** queries with presets and visualisations
4. **Explore playbooks** (cache-backed list + exploded metrics)
5. **Refactor playbooks** (extract / cluster / descriptions / post-task updates)
6. Manage **content objects** (scripts, integrations, instances, correlation rules, widgets)

**Build order:** Python package + CLI **before** any web UI. Each feature should be testable offline or against a live tenant from the command line.

---

## Documentation map

| Read first | When |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Package layers, module boundaries, web wrapper plan |
| [`docs/CREDENTIALS_AND_CACHE.md`](docs/CREDENTIALS_AND_CACHE.md) | Credential file format, cache key = host + platform + api_id |
| [`docs/FEATURES.md`](docs/FEATURES.md) | Per-feature behaviour and acceptance criteria |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phase order and dependencies |
| [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md) | Code to port from `bay/` and `ai/` |
| [`docs/UI_AND_SERVER.md`](docs/UI_AND_SERVER.md) | Dev server, nav rail, XQL history UI |
| [`docs/STORAGE.md`](docs/STORAGE.md) | JSON collections, cleanup thread |
| [`docs/PLATFORMS.md`](docs/PLATFORMS.md) | Platform ids, compat paths, experimentation workflow, operation matrix |
| [`docs/api/README.md`](docs/api/README.md) | Tenant Lists API + toolkit REST (multi-file, sample payloads) |
| [`docs/api/toolkit/WEB-API.md`](docs/api/toolkit/WEB-API.md) | **Master table** — REST routes, CLI, UI, tenant paths, platform support |
| [`docs/CONTENT-CLI.md`](docs/CONTENT-CLI.md) | **Lists / playbooks / scripts CLI** — refresh, copy, delete, refactor |
| [`docs/LISTS-AGENTS.md`](docs/LISTS-AGENTS.md) | **List Tools agent guide** — cache, copy, lab tenants |

---

## Decision tree

```
What do you need?
│
├─ Design / plan a new feature
│  → docs/FEATURES.md + docs/ARCHITECTURE.md
│
├─ Credential or cache behaviour
│  → docs/CREDENTIALS_AND_CACHE.md
│  → bay/playbook-utils/playbook_utils/credentials.py (today: host+platform only — extend with api_id)
│
├─ XQL query behaviour (presets, viz, API flow)
│  → docs/FEATURES.md § XQL
│  → bay/utilities/xql-query-monitor.html + README.md
│  → ai/guidance-cache/cortex-xql-documentation.md
│
├─ Playbook metrics / exploded view
│  → docs/FEATURES.md § Playbooks
│  → ai/scripts/xsoar_playbook_metrics.py
│  → ai/guidance-sources/xsoar-6-data-schema.md
│
├─ Playbook refactor (extract-multi, descriptions, task updates)
│  → bay/playbook-utils/AGENTS.md (reference implementation)
│  → cortex_ps_toolkit/playbooks/refactor.py (bridge via bay/playbook-utils)
│  → CLI: playbooks refactor / refactor-preview / update-tasks
│  → Web: Analysis accordion → Refactor (presets, WS progress); POST /api/playbooks/refactor/*
│  → WS jobs: playbooks.refactor.execute, playbooks.refactor.workflow
│  → MFEC benchmark: scripts/benchmark_mfec_refactor.py → data/refactor-benchmarks/
│
├─ Content types (scripts, integrations, correlation rules, widgets)
│  → docs/FEATURES.md § Content management
│  → ai/guidance-cache/xsoar--xsoar-8-core-api.md
│
├─ XSOAR Lists (refresh cache, CRUD, copy between tenants)
│  → docs/LISTS-AGENTS.md  ← start here
│  → docs/api/lists/README.md + per-platform pages
│  → python3 -m cortex_ps_toolkit lists refresh --profile <slug>
│
├─ Which platforms support an operation?
│  → docs/PLATFORMS.md
│  → python3 -m cortex_ps_toolkit platforms list
│  → cortex_ps_toolkit/platforms.py OPERATIONS registry
│
└─ API paths / compat / cross-platform experiments
   → docs/PLATFORMS.md § Compatibility API paths + How to experiment
   → cortex_ps_toolkit/core/paths.py (`xsoar_shaped_path`, `XSOAR_COMPAT_PLATFORMS`)
   → bay/playbook-utils/README.md § APIs by tenant
   → python3 -m tools.cortex_docs search "<topic>" from ai/
```

---

## Implementation rules (when coding starts)

1. **Python first** — every web feature must call a library function or CLI subcommand; no business logic only in the frontend.
2. **Credential-scoped cache** — cache path includes API key id so parallel profiles on one tenant do not collide.
3. **Platform abstraction** — path rules live in `core/paths.py` + `core/client.py`; features call `xsoar_shaped_path()`, not ad-hoc URL building.
4. **Compat paths** — for XSOAR-shaped content APIs on xsiam/xdr3/xdr5/agentix, use `/xsoar/public/v1/...`; on xsoar6 strip that prefix. Assume **xdr3 ≈ xdr5** until a lab tenant says otherwise. Mark unverified platforms **experimental** in `OPERATIONS`.
5. **Debug artifacts** — long-running operations write JSON + text under `.debug/<timestamp>-<command>/` (pattern from playbook-utils).
6. **Tests** — 199 unit tests (offline fixtures/mocks) + 83 integration tests (live lab tenants). Run unit: `pytest tests/ --ignore=tests/integration -q`. Integration (after `credentials import-lab`): `pytest tests/integration -m integration -v`. Lab tenants (no XDR 3): `personal-xsoar6`, `xsoar-japac-dev`, `psojapac-xsiam`, `cortex-cs-xdr5`, `cortex-cs-agentix`. Coverage overview: `docs/ARCHITECTURE.md` § Testing strategy.
7. **Cache TTL & concurrency** — default elective TTL **5 minutes** (`data/collections/settings.json`, `CORTEX_PS_CACHE_TTL_SEC`, or per-profile `cache_ttl_seconds`). Per-host in-flight cap **5**, global **20** (`max_inflight_per_host`, `max_inflight_global`; env `CORTEX_PS_MAX_INFLIGHT_*`). Analysis/copy planning call `ensure_*_cache` (elective; `force=True` → required). Explicit `POST /api/*/refresh` and post-mutation paths use required refresh. WebSocket `cache.refresh` is elective and parallelizes independent scopes. Runtime: `cortex_ps_toolkit/runtime/` + `workflows/cache_refresh.py`. Playbook bodies: `data/cache/{key}/playbooks/bodies/`. Status: `GET /api/cache/status?profile=`.
8. **XQL** — not on XSOAR 6/8. Web UI embeds `web/static/xql-monitor.html` (full BAY monitor features) using toolkit profile + `POST /api/xql/run`.
9. **Do not commit** `data/` (credentials, cache, query results).
10. **Playbook Tools refresh** must refresh **playbooks + scripts** together.
11. **Dev server** — `./scripts/dev-server.sh` → **http://127.0.0.1:8770/** (port 8770 avoids conflict with XQL monitor on 8765). Do not open `web/static/index.html` via `file://`.
12. **Platform gating** — register each operation in `platforms.OPERATIONS`; call `assert_operation_supported` before tenant API work.
13. **Lab credentials** — `python -m cortex_ps_toolkit credentials import-lab` from `presets/credentials/lab-sources.json` (secrets stay in gitignored `data/`).

---

## Related agent guides

| Guide | Path |
| --- | --- |
| Playbook refactor (reference impl) | `bay/playbook-utils/AGENTS.md` |
| XSOAR dev workspace | `ai/AGENTS.md` |
| Playbook YAML offline analysis | `ai/tools/playbook_yaml/README.md` |
| Incident workflow metrics | `ai/guidance-sources/xsoar-incident-workflow-analysis.md` |
