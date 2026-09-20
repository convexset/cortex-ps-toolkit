# Toolkit REST — Scripts

Wraps tenant automation/script search, get, save, and delete using the active credential profile.

## GET /api/scripts?profile={slug}

Cached scripts from `data/cache/{cache_key}/scripts/index.json`.

## GET /api/scripts/{script_id}?profile={slug}

Live automation script detail for the web viewer: metadata in `configuration`, source in `script`, plus `script_language`.

`script_id` may be a tenant UUID or script name (name lookup is used when id load fails).

**UI:** Script Tools → double-click row or **View selected**.

## POST /api/scripts/refresh

**Request:** `{ "profile": "cortex-cs-xdr5" }`

**Response `200`:** `{ "profile", "count", "cache_path", "refreshed_at", "compat_mode?", "warning?" }`

On XSIAM/XDR/AgentiX, refresh uses `POST /xsoar/public/v1/automation/search`. If compat search fails, existing cache is preserved and `warning` is set.

## POST /api/scripts/copy/preview

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "bay-xsiam-1",
  "script_ids": ["<uuid>"],
  "overwrite": false,
  "stop_on_conflict": false
}
```

## POST /api/scripts/copy

Same body as preview.

## POST /api/scripts/delete/preview

**Request:** `{ "profile": "...", "script_ids": ["<uuid>"] }`

## POST /api/scripts/delete

Same body as preview.

**Tenant API (delete):**

| Platform | Path | Body |
| --- | --- | --- |
| **xsoar6** | `POST /automation/delete` | `{"script": {"id": "<uuid>"}}` |
| **xsoar8** | `POST /xsoar/automation/delete` | `{"script": {"id": "<uuid>"}}` |
| **xsiam / xdr5 / agentix** | `POST /public_api/v1/scripts/delete` | `{"request_data": {"filter": {"field": "id", "value": "<uuid>"}}}` |

On XSOAR 8, `POST /xsoar/public/v1/automation/delete` returns **303** (not the working route).

CLI equivalent: `python3 -m cortex_ps_toolkit scripts …` — see [`CONTENT-CLI.md`](../../CONTENT-CLI.md).
