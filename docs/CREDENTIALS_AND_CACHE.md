# Credentials and cache

---

## Credential manager

### Storage

Credential profiles live in a **JSON collection** for portability:

```
data/collections/credentials.json
```

See [`STORAGE.md`](STORAGE.md) for the full storage model (collections vs cache object files, cleanup thread).

The web app and CLI read/write this file on the server filesystem. Profiles are **not** stored in browser `localStorage` (unlike the current XQL HTML monitor).

### Profile file format

```json
{
  "label": "BAY XSIAM Prod",
  "url": "https://api-bay.xdr.sg.paloaltonetworks.com",
  "id": "42",
  "key": "<api-key-secret>",
  "tenant_type": "xsiam",
  "verify_ssl": true,
  "notes": "Optional free text for operators"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `label` | Yes | Human name shown in UI/CLI |
| `url` | Yes | Tenant base URL (scheme + host) |
| `key` | Yes | API key secret |
| `id` | XSOAR 8 / XSIAM | API key ID (`Authorization` header companion) |
| `tenant_type` | Recommended | `xsoar6`, `xsoar8`, or `xsiam`; auto-detect from URL if omitted |
| `verify_ssl` | No | Default `true`; set `false` for lab IPs |
| `notes` | No | Operator documentation |
| `cache_ttl_seconds` | No | Override global elective cache TTL for this profile (minimum 30) |
| `max_inflight_per_host` | No | Override per-host API concurrency cap (shared by all profiles on same host) |
| `max_inflight_global` | No | Override global in-flight API operation cap for this profile's requests |

**Aliases:** accept `api_id` / `api_key` as synonyms during load (match playbook-utils).

### Global settings (`data/collections/settings.json`)

| Key | Default | Env override |
| --- | --- | --- |
| `cache_ttl_seconds` | `300` (5 min) | `CORTEX_PS_CACHE_TTL_SEC` |
| `max_inflight_per_host` | `5` | `CORTEX_PS_MAX_INFLIGHT_PER_HOST` |
| `max_inflight_global` | `20` | `CORTEX_PS_MAX_INFLIGHT_GLOBAL` |

Patch via `PATCH /api/settings` or edit the JSON file directly. Profile-level fields take precedence over global defaults for that credential.

### Profile identity

Each file has:

- **Filesystem slug** — derived from `label` (e.g. `bay-xsiam-prod.credentials.json`)
- **Stable profile id** — UUID stored inside the file on first save (for cache directory naming even if label changes)

### CLI operations (planned)

```bash
python -m cortex_ps_toolkit credentials list
python -m cortex_ps_toolkit credentials show --profile bay-xsiam-prod
python -m cortex_ps_toolkit credentials add --label "..." --url "..." --id "..." --key "..."
python -m cortex_ps_toolkit credentials validate --profile bay-xsiam-prod
```

`validate` performs a minimal API call (e.g. playbook search or `get_me`) and reports platform detection.

### Security

- Directory permissions: readable only by the operator user
- Never commit `data/credentials/` (see root `.gitignore`)
- Web UI: credentials displayed masked; full key only on create/edit forms over localhost
- Prefer **separate profiles** for read-only XQL vs read-write content work

---

## Content cache

### Cache key (credential-scoped)

```
cache_key = sanitize(host) / tenant_type / api_id_or_anonymous
```

Examples:

| Profile | Cache directory |
| --- | --- |
| BAY prod key `42` | `data/cache/api-bay.xdr.sg.paloaltonetworks.com/xsiam/42/` |
| BAY prod key `99` | `data/cache/api-bay.xdr.sg.paloaltonetworks.com/xsiam/99/` |
| XSOAR 6 lab (no api id) | `data/cache/192.168.1.10/xsoar6/_/` |

This ensures **different API key IDs on the same tenant never share cache entries**, even when URL and tenant type match.

**Migration note:** playbook-utils today uses `host/tenant_type` only. When porting, update cache root construction — do not reuse playbook-utils cache dirs without the api_id segment.

### Cache layout

```
data/cache/{cache_key}/
  meta.json                 # fetched_at, ttl, scopes refreshed, counts
  index.json                # quick lookup id → name, type, summary fields
  playbooks/
    {playbook_id}.json
  scripts/
    {script_id}.json
  integrations/
    {integration_id}.json
  integration_instances/
    {instance_id}.json
  correlation_rules/        # XSIAM
    {rule_id}.json
  widgets/
    {widget_id}.json
  manifest.txt              # human-readable inventory (optional)
```

### Cache metadata (`meta.json`)

```json
{
  "profile_id": "uuid",
  "url": "https://...",
  "tenant_type": "xsiam",
  "api_id": "42",
  "fetched_at": 1758086400.0,
  "ttl_seconds": 3600,
  "scopes": {
    "playbooks": { "complete": true, "count": 587, "fetched_at": 1758086400.0 },
    "scripts": { "complete": false, "count": 120, "fetched_at": 1758086500.0 }
  }
}
```

### TTL, refresh modes, and locking

| Mode | When | Behaviour |
| --- | --- | --- |
| **Elective** | Analysis, copy planning, WebSocket `cache.refresh` | Skip tenant fetch when index is TTL-fresh; double-checked under per-scope lock |
| **Required** | `POST /api/*/refresh`, `ensure_*_cache(force=True)`, after mutations | Always fetch from tenant; still serialized by lock |

| Event | Behaviour |
| --- | --- |
| TTL expired (elective) | Next `ensure_*_cache` triggers refresh for that scope |
| Content upload/delete via toolkit | Required refresh of affected scope after write |
| Manual HTTP refresh | Required refresh (ignores TTL) |
| Credential key rotated | New api_id → new cache dir automatically |

Default elective TTL: **5 minutes** (global settings or per-profile `cache_ttl_seconds`).

Implementation: `cache/ensure.py` (feature entry), `cache/refresh.py` (lock + TTL skip), `workflows/cache_refresh.py` (parallel multi-scope refresh via `GraphExecutor`).

### Scoped refresh

Not every operation needs a full tenant pull:

```bash
python -m cortex_ps_toolkit cache refresh --profile bay-xsiam-prod --scope playbooks+scripts
python -m cortex_ps_toolkit cache refresh --profile bay-xsiam-prod --scope scripts
python -m cortex_ps_toolkit cache refresh --profile bay-xsiam-prod --scope all
python -m cortex_ps_toolkit cache status --profile bay-xsiam-prod
```

**UI rule:** **Playbook Tools → Refresh cache** always runs `playbooks+scripts`. **Script Tools → Refresh** runs `scripts` only.

### Index vs full objects

- **index.json** — lightweight rows for list UIs (playbook name, task count, modified, tags)
- **Per-object JSON** — full API payload for drill-down, compare, refactor, metrics

Playbook list UI reads index only; exploded metrics loads root + referenced subs from `playbooks/*.json`.

---

## Preset storage (XQL)

Separate from content cache but same credential-aware **server storage** concept:

| Preset tier | Location | Scope |
| --- | --- | --- |
| **Application** | `presets/xql/application/*.json` | Shipped with toolkit (Case Resolution, Playbook Run Performance, …) |
| **Server** | `data/presets/xql/<profile_slug>/*.json` | Shared on this machine for a credential profile |
| **Local export** | User downloads TSV/JSONL | Offline analysis (no credentials needed) |

Preset file shape (draft):

```json
{
  "name": "Playbook Run Performance",
  "description": "Run counts and duration stats by playbook",
  "timeframe_ms": 172800000,
  "query": "dataset = playbook_runs | ...",
  "suggested_visualizations": ["playbook_run_performance"]
}
```

Application presets mirror those in `bay/utilities/xql-query-monitor.html` today.
