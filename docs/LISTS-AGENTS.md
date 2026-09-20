# List Tools — Agent Guide

**Read this file** when working with XSOAR **Lists** (cache refresh, CRUD, copy between tenants).

Human overview: [`FEATURES.md`](FEATURES.md) (planned). Tenant API reference: [`api/lists/README.md`](api/lists/README.md). Toolkit REST: [`api/toolkit/lists.md`](api/toolkit/lists.md).

Package root: `/Users/weichen/Downloads/dev/cortex-ps-toolkit`

---

## Index

| Section | When |
| --- | --- |
| [Purpose](#purpose) | What List Tools does |
| [Prerequisites](#prerequisites) | Credentials, platform support |
| [Decision tree](#decision-tree) | CLI vs web vs library |
| [CLI commands](#cli-commands) | Full command reference |
| [Web UI](#web-ui) | Dev server + List Tools panel |
| [API paths by platform](#api-paths-by-platform) | xsoar6 / xsoar8 / compat |
| [Cache layout](#cache-layout) | On-disk index |
| [Copy between tenants](#copy-between-tenants) | Behaviour and pitfalls |
| [Lab verification](#lab-verification) | Tested profiles (2026-09-17) |
| [Module map](#module-map) | Python modules |
| [Tests](#tests) | pytest |
| [Workflow checklist](#workflow-checklist) | Agent steps |
| [Related docs](#related-docs) | External references |

---

## Purpose

Manage XSOAR **Lists** content objects on live tenants:

- **Refresh cache** — `GET` all lists → `data/cache/{cache_key}/lists/index.json`
- **Navigate** — list/search cached metadata (id, name, type, modified)
- **Create / update / delete** — `POST .../lists/save`, `POST .../lists/delete`
- **Copy to another tenant** — read source list body, save on target profile

Does **not** replace pack-based list deployment; intended for PS lab work and tenant-to-tenant migration.

---

## Prerequisites

1. **Credential profile** in `data/collections/credentials.json` (import lab or add via CLI/web).
2. **Platform support** — `content.lists.manage` in `platforms.py`:
   - **documented:** `xsoar6`, `xsoar8`
   - **experimental:** `xsiam`, `xdr3`, `xdr5`, `agentix` (compat path `/xsoar/public/v1/lists`)
3. **TLS:** set `verify_ssl: false` on self-signed XSOAR 6 hosts (e.g. `personal-xsoar6`).

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python3 -m cortex_ps_toolkit credentials import-lab
python3 -m cortex_ps_toolkit credentials list
```

---

## Decision tree

```
Need to work with Lists?
│
├─ One-off / automation / agent session
│  → CLI (below)
│
├─ Operator browsing + copy in browser
│  → ./scripts/dev-server.sh → http://127.0.0.1:8770/#/lists
│
├─ Which API path for this platform?
│  → docs/PLATFORMS.md § Compatibility API paths
│  → docs/api/lists/{platform}.md
│
└─ Implement new list-related feature
   → cortex_ps_toolkit/lists/ + register in platforms.OPERATIONS
   → Use xsoar_shaped_path() from core/paths.py
```

---

## CLI commands

Run from package root:

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit

# Refresh tenant → cache
python3 -m cortex_ps_toolkit lists refresh --profile xsoar-japac-dev

# Show cached lists (stdout table)
python3 -m cortex_ps_toolkit lists list --profile personal-xsoar6

# Show one list (by id or name)
python3 -m cortex_ps_toolkit lists show --profile personal-xsoar6 --name InternalDomains

# Create or update
python3 -m cortex_ps_toolkit lists save --profile personal-xsoar6 \
  --name MyList --data "line1\nline2" --type plain_text

# Delete (bulk — repeat --id)
python3 -m cortex_ps_toolkit lists delete-preview --profile personal-xsoar6 --id MyList
python3 -m cortex_ps_toolkit lists delete --profile personal-xsoar6 --id MyList --id OtherList

# Copy to another tenant
python3 -m cortex_ps_toolkit lists copy-preview \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --id InternalDomains --stop-on-conflict

python3 -m cortex_ps_toolkit lists copy \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --id InternalDomains --overwrite
```

Playbooks and scripts use the same subcommand names — see [`CONTENT-CLI.md`](CONTENT-CLI.md).

---

## Web UI

**Important:** Port **8770** (not 8765 — that port is used by `bay/utilities/serve-xql-monitor.py`).

```bash
./scripts/dev-server.sh
# → http://127.0.0.1:8770/
```

| Action | UI location |
| --- | --- |
| Refresh cache | List Tools → **Refresh cache** |
| Browse lists | List Tools grid (select rows) |
| Copy lists | List Tools → target profile → **Copy selected** |

API: [`api/toolkit/lists.md`](api/toolkit/lists.md). Health check: `GET /api/health`.

---

## API paths by platform

| Platform | Lists base path | Auth |
| --- | --- | --- |
| xsoar8 | `/xsoar/public/v1/lists` | `Authorization` + `x-xdr-auth-id` |
| xsoar6 | `/lists` | `Authorization` (often no auth id) |
| xsiam, xdr3, xdr5, agentix | `/xsoar/public/v1/lists` | `Authorization` + `x-xdr-auth-id` |

| Operation | Method | Path suffix |
| --- | --- | --- |
| Get all | GET | `` |
| Download body | GET | `/download/{list_id}` |
| Save | POST | `/save` |
| Delete | POST | `/delete` |

Per-platform samples: [`api/lists/`](api/lists/). Official XSOAR 8: [Lists API](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/lists).

Path resolution code: `cortex_ps_toolkit/core/paths.py` → `xsoar_shaped_path()`.

---

## Cache layout

```
data/cache/{sanitize(host)}/{tenant_type}/{api_id}/lists/index.json
```

Index shape:

```json
{
  "version": 1,
  "profile_slug": "xsoar-japac-dev",
  "cache_key": "api-xsoar-japac-test.crtx.au.paloaltonetworks.com/xsoar8/43",
  "refreshed_at": "2026-09-17T07:48:51Z",
  "count": 47,
  "lists": [ { "id": "...", "name": "...", "type": "plain_text", "data": "..." } ]
}
```

Refresh runs automatically after save, delete, and copy on the affected profile.

---

## Copy between tenants

Module: `cortex_ps_toolkit/lists/copy.py` → `copy_lists_to_tenant()`.

1. Resolve each list on **source** (cache; download if `truncated` or empty `data`).
2. Refresh **target** cache for name lookup.
3. **Save** on target — create or update if `overwrite=true`.
4. Skip if name exists and `overwrite=false` → status `skipped`.

Both profiles must support `content.lists.manage` on their platform types.

---

## Lab verification

| Profile | Platform | Refresh | Save+delete smoke |
| --- | --- | --- | --- |
| `personal-xsoar6` | xsoar6 | ✓ 2 lists | ✓ |
| `xsoar-japac-dev` | xsoar8 | ✓ 47 lists | ✓ |
| `psojapac-xsiam` | xsiam | ✓ 150 lists | ✓ |
| `cortex-cs-xdr5` | xdr5 | ✓ 8 lists | ✓ |
| `cortex-cs-agentix` | agentix | ✓ 11 lists | ✓ |

Smoke-test list name: `_CPTK_TOOLKIT_TEST` (create then delete).

---

## Module map

```
cortex_ps_toolkit/
├── lists/
│   ├── api.py          # HTTP: fetch, save, delete, download
│   ├── cache.py        # index.json read/write
│   ├── service.py      # refresh, save, delete orchestration
│   └── copy.py         # cross-tenant copy
├── core/
│   ├── client.py       # TenantClient, lists_url()
│   └── paths.py        # xsoar_shaped_path()
└── server/app.py       # REST /api/lists/*
```

---

## Tests

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python3 -m pytest tests/test_lists_paths.py tests/test_lists_copy.py tests/test_compat_paths.py -q
```

Live tests require gitignored credentials — use lab profiles above.

---

## Workflow checklist

### Refresh and inspect

1. `credentials import-lab` (or confirm profile exists)
2. `lists refresh --profile <slug>`
3. `lists list --profile <slug>` or web UI grid

### Copy lists to another tenant

1. Refresh **source** cache
2. `lists copy --from-profile A --to-profile B --id ListName [--overwrite]`
3. Refresh **target** cache and verify

### Add support for a new platform

1. Confirm compat path with `lists refresh` on lab tenant
2. Update `platforms.OPERATIONS` (`experimental` → `documented` when stable)
3. Add [`api/lists/{platform}.md`](api/lists/) + sample under `api/lists/samples/`
4. Update [Lab verification](#lab-verification) table here

---

## Related docs

| Doc | Path |
| --- | --- |
| Platform compat paths | [`PLATFORMS.md`](PLATFORMS.md) |
| API index | [`api/README.md`](api/README.md) |
| Credentials | [`CREDENTIALS_AND_CACHE.md`](CREDENTIALS_AND_CACHE.md) |
| Web server | [`UI_AND_SERVER.md`](UI_AND_SERVER.md) |
| Playbook refactor (similar agent pattern) | `bay/playbook-utils/AGENTS.md` |
