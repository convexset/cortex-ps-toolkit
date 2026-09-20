# Architecture

Cortex PS Toolkit is a **local professional-services workbench** for Cortex tenants. It is designed to run on an analyst's machine (or a shared jump host), not as a hosted multi-tenant service.

---

## Design principles

| Principle | Rationale |
| --- | --- |
| **Python first** | Libraries and CLIs are easier to test, script in CI, and reuse from notebooks than UI-only logic |
| **Thin web layer** | The future web app calls the same Python services the CLI uses |
| **Credential-scoped cache** | Different API keys on the same tenant may see different content or permissions |
| **Explicit platform support** | XSOAR 6, XSOAR 8, and XSIAM differ in auth and endpoints — abstract once, test per platform |
| **Proven patterns** | Port behaviour from `bay/playbook-utils` and `bay/utilities` rather than redesigning |

---

## Layer model

```
┌─────────────────────────────────────────────────────────────┐
│  Web UI (phase 4) — local server, same-origin API proxy     │
├─────────────────────────────────────────────────────────────┤
│  CLI (phase 1–3) — python -m cortex_ps_toolkit <command>    │
├─────────────────────────────────────────────────────────────┤
│  Feature modules                                            │
│  xql/  playbooks/  content/                                 │
├─────────────────────────────────────────────────────────────┤
│  Core                                                        │
│  credentials/  cache/  client/  debug/  presets/            │
└─────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
   data/collections/              data/cache/
   (JSON indexes)            (per-profile object files)
```

### Core (`cortex_ps_toolkit/core/`)

| Module | Responsibility |
| --- | --- |
| `credentials.py` | Load/save/list credential profiles; validate URL + key + api_id + tenant_type |
| `cache.py` | Generic TTL cache with manifest, index, invalidation; profile-scoped root path |
| `client.py` | HTTP session, auth headers, platform routing (XSOAR 6/8 vs XSIAM public API) |
| `debug.py` | Timestamped debug directories, JSON/text writers |
| `presets.py` | Load merged preset catalog (application + server + local paths) |
| `maintenance.py` | Background cleanup thread (15 min); retention policies |
| `collections.py` | Read/write versioned JSON collection files |

### Feature modules

| Package | Responsibility |
| --- | --- |
| `xql/` | Start/poll/stream XQL; preset expansion; result normalisation; viz rule engine |
| `playbooks/` | Cache refresh; list/summary; tree walk; metrics; refactor orchestration |
| `content/` | Scripts, integrations, instances, correlation rules, widgets — list/get/cache/compare |

Each feature module accepts a **resolved credential profile** and returns **structured dataclasses / JSON**, not HTML.

---

## Credential and cache relationship

```
Credential profile "BAY Prod (readonly)"
  url, api_id, key, tenant_type
        │
        ▼
  cache_key = f"{host}/{tenant_type}/{api_id}"
        │
        ▼
  data/cache/{cache_key}/
    meta.json
    index.json
    playbooks/{id}.json
    scripts/...
    integrations/...
```

See [`STORAGE.md`](STORAGE.md) and [`CREDENTIALS_AND_CACHE.md`](CREDENTIALS_AND_CACHE.md) for file formats.

**Difference from playbook-utils today:** `bay/playbook-utils` uses `cache_key = host/tenant_type` only. This toolkit **adds `api_id`** so two keys on the same tenant do not share cache entries.

---

## Playbook refactor integration

Two viable strategies (decide during phase 3 implementation):

| Strategy | Pros | Cons |
| --- | --- | --- |
| **A. Vendored port** | Copy `playbook_utils` subset into `cortex_ps_toolkit/playbooks/refactor/` | Duplication; manual sync |
| **B. Dependency** | Add `bay/playbook-utils` as editable path dependency | Cross-repo coupling |
| **C. Extract shared package** | Move `playbook_utils` to `ai/` or a small shared lib | Best long-term; more upfront work |

**Recommendation:** start with **B** (editable install from `bay/playbook-utils`) for speed; migrate to **C** if both repos need independent release cycles.

Refactor behaviour to preserve (from playbook-utils):

- Leaf + cluster + combined `extract-multi`
- Round-trip compare (B) before parent upload
- `--post-task-update` before descriptions
- Playbook-level descriptions + `12-refactor-metrics.txt` debug output
- `[REFACTOR-M]` / `[REFACTOR-S]` naming conventions

---

## XQL integration

Port the **behaviour** of `bay/utilities/xql-query-monitor.html` into Python + a future web front-end:

| HTML monitor concern | Python module |
| --- | --- |
| `start_xql_query` / poll / stream | `xql/runner.py` |
| Built-in presets (Case Resolution, Playbook Run Performance, …) | `presets/application/*.json` |
| localStorage presets | `presets/local/` (server-side files) + optional browser override later |
| Timestamp column inference | `xql/schema.py` |
| Visualisation rule matching | `xql/visualizations.py` (returns chart spec JSON for Plotly) |

The web UI renders chart specs; **detection logic stays in Python** so CLI can print “suggested charts” without a browser.

---

## Playbook metrics / exploded view

Uses **cached playbook JSON** (not live search on every navigation):

1. **Index** — flat list with task counts, tags, modified time (`playbooks/index.json`)
2. **Tree walk** — resolve sub-playbook references by name/id from cache (pattern: `playbook_tree.py` in playbook-utils)
3. **Metrics** — apply `xsoar_playbook_metrics` characterisation per playbook; aggregate when viewing exploded workflow

“Exploded view” = user selects a **root playbook** → toolkit loads root + all reachable subs from cache → shows combined task counts, automation ratio, script/command inventory, and nested structure tree.

---

## Web application

| Aspect | Choice |
| --- | --- |
| **Start** | `./scripts/dev-server.sh` → `python -m cortex_ps_toolkit serve --reload --debug` |
| Deployment | Local `127.0.0.1`; optional `--host 0.0.0.0` for LAN |
| Backend | FastAPI or Flask wrapping Python services; **auto-reload** on `.py` changes in dev |
| Frontend | Single shell + **CDN** libs (Tabulator, Plotly) + fetch-driven dynamic UI ([`UI_AND_SERVER.md`](UI_AND_SERVER.md)) |
| Navigation | Icon rail: Credentials, XQL, Playbook Tools, Script Tools |
| Auth | OS file permissions on `data/`; no multi-user auth in v1 |
| CORS | Same-origin proxy — credentials stay server-side |
| Maintenance | Background thread every **15 minutes** — prune old XQL results, debug dirs ([`STORAGE.md`](STORAGE.md)) |

Full API and UI specs: [`UI_AND_SERVER.md`](UI_AND_SERVER.md).

---

## Runtime concurrency and cache refresh

Toolkit API traffic uses a **thread-based dependency graph** (`cortex_ps_toolkit/runtime/`) rather than ad-hoc threading in each feature module.

| Control | Default | Scope |
| --- | --- | --- |
| Per-host in-flight cap | **5** | Shared by all credential profiles on the same API host |
| Global in-flight cap | **20** | All tenant operations across hosts |
| Cache TTL (elective refresh) | **300s (5 min)** | Per credential profile (override) or global settings |

Credential profiles may override `cache_ttl_seconds`, `max_inflight_per_host`, and `max_inflight_global`. Global defaults live in `data/collections/settings.json` (or env vars `CORTEX_PS_*`).

### Cache refresh modes

| Mode | When | Behaviour |
| --- | --- | --- |
| **Elective** | Analysis, copy planning, WebSocket refresh | Skip fetch when index is TTL-fresh; double-checked under per-scope lock |
| **Required** | After mutations, explicit `POST /api/*/refresh` | Always fetch; still serialized by lock |

`cache/refresh.py` owns locking and TTL skip logic. `cache/ensure.py` is the feature-facing entry point (`ensure_*_cache`, `force=True` → required).

### Parallelism model

Independent scopes refresh in parallel via `GraphExecutor` (e.g. playbooks + scripts on WebSocket `all`, integration commands + instances + packs). **Failed dependencies mark dependents as failed** without running them.

Some workflows remain **sequential groups** inside their bridge until ported:

| Workflow | Parallelism |
| --- | --- |
| **Component copy** | Scripts may copy in parallel; playbooks follow dependency order (subs before root). Sequential **phases**, parallel **within** a phase where safe. |
| **Refactor / extract-multi** | **Default: sequential** (upload subs → refresh once → compare → post-task-update → descriptions → parent). **Experimental parallel variant** (`refactor_mode=parallel`, `--parallel`, or `refactor_execution_mode` in settings): parallel sub upload/compare/post-steps within each extract-multi; workflow presets with multiple steps may run Splunk+SIM refactors in parallel via `GraphExecutor`. Roll back by omitting the flag or setting mode to `sequential`. |

Do not flatten these into the global graph until the underlying operations are decomposed into independent tasks with explicit dependencies.

---

## Testing strategy

### Commands

```bash
# Unit tests only (~2s, no network)
python3 -m pytest tests/ --ignore=tests/integration -q

# Integration tests (lab credentials; ~20 min)
python3 -m pytest tests/integration -m integration -v

# Full suite (282 tests when all lab profiles configured)
python3 -m pytest -q

# Coverage (pip install pytest-cov)
python3 -m pytest tests/ --ignore=tests/integration -q \
  --cov=cortex_ps_toolkit --cov-report=term-missing:skip-covered
```

Integration tests require `python3 -m cortex_ps_toolkit credentials import-lab` and gitignored secrets under `data/`. Lab slugs: `personal-xsoar6`, `xsoar-japac-dev`, `psojapac-xsiam`, `cortex-cs-xdr5`, `cortex-cs-agentix`.

### Test inventory (282 total)

| Suite | Files | Tests | What it exercises |
| --- | --- | --- | --- |
| **Unit** | 41 files under `tests/` | 199 | Offline mocks/fixtures; no live HTTP |
| **Integration** | `tests/integration/` | 83 | Live lab tenants: validate, refresh, copy fidelity, XQL, delete/copy previews |

### Unit coverage overview (~59% line coverage)

Measured with `pytest-cov` on unit tests only (integration paths hit live APIs and are excluded from coverage runs).

| Area | Representative tests | Unit coverage | Notes |
| --- | --- | --- | --- |
| **Runtime** (`runtime/`, `workflows/`) | `test_runtime_graph.py`, `test_runtime_limits.py`, `test_cache_refresh.py` | graph 90%, limits 97%, workflows 31% | Graph + limits well covered; workflow glue exercised mainly in integration |
| **Cache** (`cache/`) | `test_cache_ttl.py`, `test_cache_query.py` | refresh 90%, ttl 77%, ensure via callers | Lock + elective/required modes |
| **Playbooks** | `test_playbooks_*` (15 files) | analysis 92%, graph 95%, yaml 95–98% | Refactor bridge 53%; delete/service lower |
| **Scripts** | `test_scripts_*` (8 files) | upload_prep 91%, copy 76% | Live API in `scripts/api.py` partial |
| **Lists** | `test_lists_*` (4 files) | delete 90%, copy 71% | service/cache integration-heavy |
| **Credentials & vault** | `test_credentials*.py`, `test_vault_store.py` | credentials 85%, vault 83–86% | |
| **Platforms & paths** | `test_platforms.py`, `test_compat_paths.py` | platforms 63%, paths 91% | |
| **Web server** | `test_web_api_routes.py`, `test_server_async.py` | app 34%, routes 20–52% | Route wiring; not full HTTP e2e |
| **Integrations** | (integration + probe docs) | service 27%, api 45% | Live refresh in integration suite |
| **XQL** | `test_xql_service.py` | service 75%, api 30% | Live XQL in integration (XSIAM/XDR/AgentiX) |
| **Content probes** | `test_copy_fidelity` (integration) | copy_probe 0% unit | Fidelity probes are integration-only |

**Well covered (>85%):** `runtime/limits`, `runtime/graph`, `cache/refresh`, playbook analysis/graph/yaml helpers, vault crypto/store, lists delete, credentials core, system validate.

**Integration-only or thin unit coverage:** `content/copy_probe.py`, `server/ws.py`, `workflows/cache_refresh.py`, integration service refresh paths, refactor bridge execution (needs live tenant + playbook-utils).

| Layer | Approach |
| --- | --- |
| Core | Unit tests with temp dirs for credentials + cache |
| Runtime | Thread-pool graph, limit semaphores, cache lock/TTL |
| XQL | Mock HTTP unit tests; live `limit 1` query in integration |
| Playbooks | Graph/metrics/yaml unit tests; copy fidelity integration |
| Content | Copy/delete preview unit tests; fidelity probes integration |
| Integration | `@pytest.mark.integration` — read/preview/copy-fidelity on lab tenants |

---

## Non-goals (v1)

- Multi-tenant SaaS hosting
- Bi-directional content pack authoring / demisto-sdk replacement
- Real-time playbook editing UI (task canvas)
- Storing credentials in a database (files only for v1)
