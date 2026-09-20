# Toolkit REST — Lists

Wraps tenant Lists API using the active credential profile.

## GET /api/lists?profile={slug}

Cached lists from `data/cache/{cache_key}/lists/index.json`.

**Response `200`:**

```json
{
  "profile": "personal-xsoar6",
  "refreshed_at": "2026-09-17T07:48:51Z",
  "count": 2,
  "lists": [ { "id": "InternalDomains", "name": "InternalDomains", "type": "plain_text" } ]
}
```

## GET /api/lists/{list_id}?profile={slug}

Full list detail for the web viewer: metadata in `configuration`, entries in `data`, plus `list_type`.

Uses cached list metadata; downloads list body from the tenant when the cache entry is truncated or has no inline `data`.

**UI:** List Tools → double-click row or **View selected**.

## POST /api/lists/refresh

**Request:** `{ "profile": "xsoar-japac-dev" }`

**Response `200`:**

```json
{
  "profile": "xsoar-japac-dev",
  "count": 47,
  "cache_path": "/path/to/data/cache/.../lists/index.json",
  "refreshed_at": "2026-09-17T07:48:51Z"
}
```

## POST /api/lists/copy/preview

**Request:** same body as copy (below). Returns plan with `items`, `counts`, `would_abort`, `conflicts`.

## POST /api/lists/delete/preview

**Request:** `{ "profile": "...", "list_ids": ["id1", "id2"] }`

## POST /api/lists/delete

**Request:** `{ "profile": "...", "list_ids": ["id1"] }`

**Response:** `{ "profile", "results", "counts" }` — `deleted`, `blocked`, `failed`, `not_found`.

## POST /api/lists/copy

**Request:**

```json
{
  "source_profile": "personal-xsoar6",
  "target_profile": "xsoar-japac-dev",
  "list_ids": ["InternalDomains"],
  "overwrite": false
}
```

**Response `200`:**

```json
{
  "source_profile": "personal-xsoar6",
  "target_profile": "xsoar-japac-dev",
  "results": [
    {
      "list_id": "InternalDomains",
      "name": "InternalDomains",
      "status": "copied",
      "target_id": "InternalDomains"
    }
  ]
}
```

Status values: `copied`, `updated`, `skipped` (name exists and `overwrite` false).

Tenant-facing API details: [`../lists/README.md`](../lists/README.md).
