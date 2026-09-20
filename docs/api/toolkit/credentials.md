# Toolkit REST — Credentials

Local dev server routes (`http://127.0.0.1:8770`). Health: `GET /api/health`. Secrets are stored server-side in `data/collections/credentials.json`.

## GET /api/credentials

List active profiles (auto-purges expired).

**Response `200`:**

```json
{
  "profiles": [
    {
      "id": "26ff6a86-93e7-41b5-9e03-9cae7b22f211",
      "label": "personal-xsoar6",
      "slug": "personal-xsoar6",
      "url": "https://xsoar6.random-samplings.org",
      "api_id": "",
      "key_masked": "9F08…",
      "tenant_type": "xsoar6",
      "verify_ssl": false,
      "notes": "Personal XSOAR 6 tenant (self-signed TLS).",
      "expires_at": null,
      "expired": false,
      "cache_key": "xsoar6.random-samplings.org/xsoar6/_",
      "cache_ttl_seconds": null,
      "max_inflight_per_host": null,
      "max_inflight_global": null,
      "created_at": "2026-09-17T07:44:36Z",
      "updated_at": "2026-09-17T07:44:36Z"
    }
  ]
}
```

## GET /api/credentials/{slug}

Single profile (masked key).

## POST /api/credentials

Create or upsert by slug.

**Request:**

```json
{
  "label": "My Tenant",
  "slug": "my-tenant",
  "url": "https://api-example.crtx.test",
  "api_id": "42",
  "key": "secret-api-key",
  "tenant_type": "xsoar8",
  "verify_ssl": true,
  "notes": "Optional",
  "expires_at": "2026-11-30",
  "cache_ttl_seconds": 600,
  "max_inflight_per_host": 5,
  "max_inflight_global": 20
}
```

Optional runtime overrides (`cache_ttl_seconds`, `max_inflight_per_host`, `max_inflight_global`) fall back to global settings in `data/collections/settings.json` when omitted or `null`.

**Response `201`:** Public profile object.

## PUT /api/credentials/{slug}

Update fields. Omit `key` or send empty string to keep existing secret.

## DELETE /api/credentials/{slug}

**Response `200`:**

```json
{ "deleted": "my-tenant", "id": "uuid" }
```

Also removes `data/cache/{cache_key}/`.

## POST /api/credentials/import-lab

Import from `presets/credentials/lab-sources.json`.

**Response `200`:**

```json
{
  "imported": 8,
  "profiles": [ "...public profile objects..." ]
}
```

## POST /api/credentials/purge-expired

**Request:** `{ "dry_run": false }`

**Response `200`:**

```json
{ "dry_run": false, "purged": ["expired-slug"] }
```

## POST /api/credentials/{slug}/validate

Live check via `GET lists` on the tenant.

**Response `200` (success):**

```json
{
  "ok": true,
  "profile": "xsoar-japac-dev",
  "tenant_type": "xsoar8",
  "check": "GET lists",
  "lists_count": 47,
  "url": "https://api-xsoar-japac-test.crtx.au.paloaltonetworks.com"
}
```

**Response `200` (failure):**

```json
{
  "ok": false,
  "profile": "my-tenant",
  "tenant_type": "xsoar8",
  "check": "GET lists",
  "error": "get all lists failed: HTTP 401 ...",
  "status_code": 401
}
```

## POST /api/credentials/{slug}/expiry

**Set:** `{ "expires_at": "end Nov 2026" }` or `{ "expires_at": "2026-11-30" }`

**Clear:** `{ "expires_at": null }`

## POST /api/credentials/{slug}/verify-ssl

**Request:** `{ "verify_ssl": false }`
