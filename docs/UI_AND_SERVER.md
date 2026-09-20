# UI, dev server, and navigation

How operators **run** the toolkit locally, how the **web UI** is structured, and how **CDN-backed** front-end libraries combine with a dynamic SPA-style experience.

---

## Operator experience: one script starts the server

Primary entry point (planned):

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
./scripts/dev-server.sh
# or: python -m cortex_ps_toolkit serve
```

Opens **`http://127.0.0.1:8770/`** (default port **8770** — avoids conflict with `bay/utilities/serve-xql-monitor.py` on **8765**).

### Dev server behaviour

| Mode | Flag / env | Behaviour |
| --- | --- | --- |
| **Auto-reload** | default in dev | Python process watches `cortex_ps_toolkit/` and restarts on `.py` changes (uvicorn `--reload` or equivalent) |
| **Debug** | `--debug` or `CORTEX_PS_DEBUG=1` | Verbose logging, Werkzeug-style tracebacks on API errors, optional Flask/FastAPI debug toolbar |
| **Production-like** | `--no-reload` | Stable process for demos or shared jump host |

Implementation sketch:

```bash
# scripts/dev-server.sh
export CORTEX_PS_DATA_DIR="${CORTEX_PS_DATA_DIR:-./data}"
exec python -m cortex_ps_toolkit serve --host 127.0.0.1 --port 8770 --reload --debug "$@"
```

- **Same-origin API proxy** — browser calls `/api/...` and `/proxy/public_api/...`; server attaches credentials (pattern from `bay/utilities/serve-xql-monitor.py`).
- **Static assets** — `web/static/` served from the same process; no separate front-end build required in v1.
- **Background maintenance** — cleanup thread starts with the server (see [Storage cleanup](#storage-cleanup-thread)).

CLI subcommands remain available while the server is stopped (`python -m cortex_ps_toolkit cache refresh …`).

---

## Front-end approach: CDN libraries + dynamic UI

### CDN-hosted dependencies

Load UI libraries from public CDNs (no bundler required for v1), matching the proven pattern in [`bay/utilities/xql-query-monitor.html`](../../bay/utilities/xql-query-monitor.html):

| Library | Use |
| --- | --- |
| **Tabulator** | Grids (playbook list, script list, XQL results) |
| **Plotly.js** | Charts (XQL visualisations, metrics) |
| **Optional: Alpine.js or petite-vue** | Lightweight reactivity for panels, modals, nav state |

**Benefits:** fast iteration, readable `web/static/app.js`, easy to inspect in DevTools.

**Trade-off:** offline use requires network for first load; document optional vendoring under `web/static/vendor/` for air-gapped installs (later).

### Dynamic interactions (modern SPA feel)

Without a heavy React/Vue build pipeline:

- **Fetch API** + JSON REST endpoints — partial page updates, no full reload
- **Client-side routing** — hash or History API routes per nav section (`#/xql`, `#/playbooks`, …)
- **Optimistic UI** where safe (e.g. preset rename); poll or SSE for long XQL runs and cache refresh
- **Modals / slide panels** for credential edit, refactor wizard, copy-to-tenant target picker
- **Keyboard shortcuts** optional later (run query, refresh cache)

Server renders a **single shell page** (`index.html`); all section content mounts into a main panel driven by JavaScript modules.

---

## Navigation panel

Fixed **icon rail** on the left. The **application logo** at the top links to the landing page (`#/`). Tool icons sit in the main rail; **API Profiles** and **Settings** are pinned to the bottom.

| Icon (concept) | Section | Route |
| --- | --- | --- |
| Logo | **Overview** (landing) | `#/` |
| Terminal / query | **XQL Query Tool** | `#/xql` |
| Diagram / flow | **Playbook Tools** | `#/playbooks` |
| Code / script | **Script Tools** | `#/scripts` |
| List / clipboard | **List Tools** | `#/lists` |
| Plug | **Integrations** | `#/integrations` |
| Key / lock | **API Profiles** (bottom) | `#/credentials` |
| Gear | **Settings** (bottom) | `#/settings` |

Global **active credential profile** selector in the header (visible on tool sections that need a profile).

### Landing page

Route: `#/` (default when opening the app root URL).

Overview cards link to each toolkit section.

### API Profiles

Route: `#/credentials`.

| Action | UI | API |
| --- | --- | --- |
| List profiles | Tabulator grid | `GET /api/credentials` |
| Add / edit | Modal form | `POST /api/credentials`, `PUT /api/credentials/{slug}` |
| Delete | Row action | `DELETE /api/credentials/{slug}` |
| Validate | Row action (GET lists ping) | `POST /api/credentials/{slug}/validate` |
| Import lab | Toolbar | `POST /api/credentials/import-lab` |
| Purge expired | Toolbar | `POST /api/credentials/purge-expired` |

Masked secrets in grid; full key only on create or when explicitly entered on edit. Storage: `data/collections/credentials.json`. See [`api/toolkit/credentials.md`](api/toolkit/credentials.md).

### XQL Query Tool

See [XQL section features](#xql-query-tool-ui) below.

### Playbook Tools

Primary workspace for cached playbooks. Sub-actions (toolbar or sub-nav):

| Action | Description |
| --- | --- |
| **Navigate / refresh cache** | Browse playbook tree from cache; **Refresh** pulls **playbooks and scripts** for active profile (single action — playbook analysis depends on script names) |
| **Refactor playbooks** | Leaf/cluster extract wizard (wraps playbook-utils flow) |
| **Copy selected playbooks** | Export/upload selected playbook YAML to another credential profile (target tenant) |
| **Copy component sub-playbooks and scripts** | For selected root playbook(s): resolve reachable subs + referenced automation scripts; copy full dependency set to target tenant |

Playbook **exploded metrics** (structure tree, automation ratio) live in the navigate view when a playbook is selected.

### Script Tools

| Action | Description |
| --- | --- |
| **Navigate / refresh cache** | Browse scripts from cache index; refresh **scripts scope only** |
| **Copy selected scripts** | Upload selected scripts to another credential profile |

Note: **Playbook Tools → Refresh** always refreshes **both** `playbooks` and `scripts` scopes. Script Tools refresh is scripts-only when operators need a lighter pull.

### List Tools

| Action | Description |
| --- | --- |
| **Navigate / refresh cache** | Tabulator grid of cached lists for active profile; **Refresh cache** calls tenant Lists API and updates `data/cache/.../lists/index.json` |
| **Copy lists to other tenant** | Select rows, pick target profile, optional overwrite; copies list name, body, type, and description via Lists save API |

CLI equivalents:

```bash
python -m cortex_ps_toolkit lists refresh --profile xsoar-japac-dev
python -m cortex_ps_toolkit lists copy --from-profile personal-xsoar6 --to-profile xsoar-japac-dev --id MyList
```

---

## XQL Query Tool UI

### Query execution

- Preset picker (application + server presets)
- Query editor, timeframe, run/stop
- Results grid (Tabulator) + suggested charts (Plotly)
- Export TSV / JSONL

### Query history (server-stored)

Every completed or saved run is recorded in a **query history collection** with a stable **query ID**.

Storage: `data/collections/xql_queries.json` (+ optional result files — see [`STORAGE.md`](STORAGE.md)).

**History list row:**

| Column | Content |
| --- | --- |
| Query ID | Short uuid or monotonic id (e.g. `xq_20260917_001`) |
| Label | Preset name or first line of query |
| Ran at | Timestamp |
| Profile | Credential profile used |
| Row count | From API metrics when available |
| Status | ok / failed / imported |

**Hover on Query ID (or row):** tooltip/popover shows **full query text**, timeframe, and profile.

**Click row / Load:** restores results from stored artifact (`data/cache/.../xql_results/{query_id}.jsonl`) and re-applies schema detection + visualisations — no re-run unless operator chooses **Re-run**.

History supports:

- Load past results offline (from stored JSONL)
- Compare two query IDs (future)
- Delete entry (cleanup thread may also prune by age)

---

## Storage cleanup thread

Started with the dev server; runs every **15 minutes** (configurable: `CORTEX_PS_CLEANUP_INTERVAL_SEC=900`).

| Target | Policy (defaults) |
| --- | --- |
| XQL result files | Remove results older than **7 days** unless pinned in history metadata |
| Debug directories (`.debug/`) | Remove dirs older than **3 days** |
| Stale cache scopes | Optional: drop scope data past TTL + grace period if not accessed |
| Orphan files | Remove `xql_results/{id}.*` with no entry in `xql_queries.json` |
| Temp upload chunks | Remove incomplete multipart temp files |

Cleanup actions append to `data/collections/cleanup_log.json` (last N entries) for operator visibility in a future “Maintenance” panel.

Manual trigger: `POST /api/maintenance/cleanup` or CLI `python -m cortex_ps_toolkit maintenance cleanup --dry-run`.

---

## API routes (illustrative)

```
GET  /                          → shell HTML
GET  /api/credentials
POST /api/credentials
GET  /api/credentials/{slug}
PUT  /api/credentials/{slug}
DELETE /api/credentials/{slug}
POST /api/credentials/import-lab
POST /api/credentials/purge-expired
POST /api/credentials/{slug}/validate
POST /api/credentials/{slug}/expiry
POST /api/credentials/{slug}/verify-ssl

GET  /api/cache/status?profile=
POST /api/cache/refresh?profile=&scope=playbooks|scripts|playbooks+scripts

GET  /api/playbooks?profile=
GET  /api/playbooks/{id}/metrics?recursive=true
POST /api/playbooks/refactor/preview
POST /api/playbooks/refactor/execute
POST /api/playbooks/refactor/update-tasks/preview
POST /api/playbooks/refactor/update-tasks
POST /api/playbooks/copy
POST /api/playbooks/copy-components

GET  /api/scripts?profile=
POST /api/scripts/copy
POST /api/scripts/refresh

GET  /api/lists?profile=
POST /api/lists/refresh
POST /api/lists/copy

GET  /api/xql/presets
POST /api/xql/run
GET  /api/xql/history?profile=
GET  /api/xql/history/{query_id}
POST /api/xql/history/{query_id}/load

POST /api/maintenance/cleanup
POST /proxy/public_api/...       → tenant API forward
```

---

## Wireframe (ASCII)

```
┌──┬──────────────────────────────────────────────────────────────┐
│🔑│  Cortex PS Toolkit          [Profile: BAY XSIAM ▼]           │
│  ├──────────────────────────────────────────────────────────────┤
│📊│  Playbook Tools                                              │
│  │  [Refresh cache] [Refactor…] [Copy selected] [Copy components]│
│📋│  ┌─────────────┬──────────────────────────────────────────┐  │
│  │  │ Playbooks   │  Metrics / tree for selected playbook    │  │
│⚙ │  │ (list)      │                                          │  │
│  │  └─────────────┴──────────────────────────────────────────┘  │
└──┴──────────────────────────────────────────────────────────────┘
     ↑ icons only; title tooltip on hover
```
