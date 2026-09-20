# Storage model

All durable state is stored as **JSON collections and JSON object files** under `data/` for portability, readability, and easy backup (zip the folder).

No SQLite or embedded DB in v1.

---

## Design goals

| Goal | Approach |
| --- | --- |
| **Portable** | Copy `data/` to another machine; paths relative to `CORTEX_PS_DATA_DIR` |
| **Readable** | Operators can open JSON in an editor; git-friendly for non-secret configs |
| **Credential-scoped** | Cache and history keyed by profile id |
| **Bounded disk use** | Background cleanup every 15 minutes (see [`UI_AND_SERVER.md`](UI_AND_SERVER.md)) |

---

## Directory layout

```
data/
├── collections/                    # Index / manifest JSON (small, frequently read)
│   ├── credentials.json            # All credential profiles (secrets in same file — gitignored)
│   ├── xql_queries.json            # Query history index (metadata + pointer to results)
│   ├── xql_presets.json            # Server-side XQL presets (per profile or global)
│   └── cleanup_log.json            # Recent cleanup actions
│
└── cache/
    └── {host}/{tenant_type}/{api_id}/
        ├── meta.json               # Cache freshness, scope counts
        ├── index.json              # Unified index: playbooks, scripts, …
        ├── playbooks/
        │   └── {playbook_id}.json  # One file per playbook (large objects split out)
        ├── scripts/
        │   └── {script_id}.json
        ├── xql_results/
        │   └── {query_id}.jsonl    # Result payload (may be large)
        └── debug_runs/               # Optional: last refactor debug bundle refs
            └── {run_id}/
                └── manifest.json
```

### Collections vs object files

| Type | Example | Purpose |
| --- | --- | --- |
| **Collection** | `credentials.json`, `xql_queries.json` | Array or map of records; loaded whole or paged in app |
| **Object file** | `playbooks/abc-uuid.json` | Large tenant payload; referenced from `index.json` |
| **Result blob** | `xql_results/xq_001.jsonl` | Stream export; referenced from history collection |

**Why split large objects:** keeps collection files small; cleanup can delete result blobs independently.

---

## Collection schemas (draft)

### `credentials.json`

```json
{
  "version": 1,
  "profiles": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "label": "BAY XSIAM Prod",
      "slug": "bay-xsiam-prod",
      "url": "https://api-bay.xdr.sg.paloaltonetworks.com",
      "api_id": "42",
      "key": "<secret>",
      "tenant_type": "xsiam",
      "verify_ssl": true,
      "notes": "",
      "created_at": "2026-09-17T05:00:00Z",
      "updated_at": "2026-09-17T05:00:00Z"
    }
  ]
}
```

Single file for portability; entire `data/` directory is gitignored except optional `data/.gitkeep`.

Alternative later: one file per profile under `data/collections/credentials/{id}.json` if multi-operator merge conflicts become an issue.

### `xql_queries.json`

```json
{
  "version": 1,
  "queries": [
    {
      "id": "xq_20260917_001",
      "profile_id": "550e8400-...",
      "label": "Playbook Run Performance",
      "query": "dataset = playbook_runs | ...",
      "timeframe_ms": 604800000,
      "preset_name": "Playbook Run Performance",
      "ran_at": "2026-09-17T05:30:00Z",
      "status": "ok",
      "row_count": 142,
      "result_path": "cache/.../xql_results/xq_20260917_001.jsonl",
      "suggested_visualizations": ["playbook_run_performance"],
      "pinned": false
    }
  ]
}
```

UI **hover on `id`** shows full `query` + timeframe. **Load** reads `result_path` and hydrates grid + charts.

### `index.json` (per cache root)

```json
{
  "version": 1,
  "playbooks": [
    { "id": "...", "name": "...", "task_count": 147, "modified": "..." }
  ],
  "scripts": [
    { "id": "...", "name": "...", "type": "python" }
  ]
}
```

Full playbook/script bodies live in sibling directories.

---

## Refresh scope semantics

| UI action | Scopes refreshed |
| --- | --- |
| Playbook Tools → **Refresh cache** | `playbooks` + `scripts` (always together) |
| Script Tools → **Refresh cache** | `scripts` only |
| CLI `cache refresh --scope all` | All implemented scopes |

Rationale: playbook metrics and refactor flows resolve **script names** from the automation catalog; stale scripts break YAML export and task labels.

---

## Cleanup policy (15-minute thread)

Configurable via `data/collections/settings.json` or environment:

```json
{
  "cleanup_interval_sec": 900,
  "xql_result_retention_days": 7,
  "debug_retention_days": 3,
  "respect_pinned_queries": true
}
```

Cleanup steps each cycle:

1. Scan `xql_queries.json` — drop unpinned entries past retention; delete orphaned `result_path` files
2. Scan `.debug/` at project root — remove old run directories
3. Log summary to `cleanup_log.json` (cap at 100 entries)
4. Optional: vacuum `index.json` entries whose object files are missing

**Dry-run** mode logs intended deletes without removing files.

---

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CORTEX_PS_DATA_DIR` | `./data` | Root for collections + cache |
| `CORTEX_PS_CLEANUP_INTERVAL_SEC` | `900` | Background cleanup period |
| `CORTEX_PS_DEBUG` | `0` | Verbose server logging |

---

## Backup and migration

```bash
# Portable backup (exclude if sharing — contains secrets)
tar czf cortex-ps-backup.tgz data/

# Restore on another host
export CORTEX_PS_DATA_DIR=/path/to/restored/data
./scripts/dev-server.sh
```

Collection files include `"version"` for forward-compatible migrations (load old version → rewrite to current on save).
