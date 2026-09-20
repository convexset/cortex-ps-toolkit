# API Keys management compatibility probe

Lab-verified **Get existing API Keys**, **Generate an API Key**, and **Delete API Keys** paths for Cortex cloud tenants, probed **2026-09-20** with API key authentication (`Authorization` + `x-xdr-auth-id`).

**Scope:** **xsoar8**, **xsiam**, **xdr5**, **agentix** only.

**Helpers:** `cortex_ps_toolkit/core/paths.py` — `api_keys_get_url()`, `api_keys_generate_url()`, `api_keys_delete_url()`.

**Related:** [system-management-probe.md](system-management-probe.md) (users / RBAC), [../PLATFORMS.md](../PLATFORMS.md).

---

## Documentation sources

| Platform | API Keys docs | Get existing API Keys documented? |
| --- | --- | --- |
| xsoar8 | [XSOAR 8 API Keys](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/api-keys) | **No** (generate + delete only) |
| xsiam | [XSIAM API Keys](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/api-keys) | Yes |
| xdr5 | [XDR 5 API Keys](https://cortex-docs.paloaltonetworks.com/xdr-5-api/cortex-platform/api-keys) | Yes |
| agentix | [AgentiX API Keys](https://cortex-docs.paloaltonetworks.com/agentix-api/cortex-agentix/api-keys) | Yes |

All four platforms share host-root paths under **`/public_api/v1/api_keys/*`**.

---

## Capability matrix

| Operation | xsoar8 | xsiam | xdr5 | agentix |
| --- | --- | --- | --- | --- |
| Get existing API Keys | ✓† | ✓ | ✓ | ✓ |
| Generate an API Key | ✓ | ✓ | ✓ | ✓ |
| Delete API Keys | ✓ | ✓ | ✓ | ✓ |

† **Undocumented on XSOAR 8** but **`POST /public_api/v1/api_keys/get_api_keys` works** with the same payload as XSIAM/XDR (lab 2026-09-20). Alternate paths `/api_keys/get` and `/api_keys/list` → **500** on all probed platforms.

---

## Get existing API Keys

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/api_keys/get_api_keys` | `api_keys_get_url(host)` |

**Request body (list all):**

```json
{
  "request_data": {
    "filters": []
  }
}
```

**Optional filters** (AND-combined): `expiration` (`gte` / `lte`, epoch ms), `roles` (`contains`, string array), `id` (`in`, integer array).

**Optional pagination / sort:** `search_from`, `search_to`, `sort: { "field": "expiration"|"roles", "keyword": "asc"|"desc" }`.

**Response shape:**

| Platform | Payload keys (typical) |
| --- | --- |
| xsoar8, xsiam, xdr5 | `reply.DATA`, `reply.FILTER_COUNT`, `reply.TOTAL_COUNT` |
| agentix | `reply.data`, `reply.filter_count`, `reply.total_count` (lowercase per AgentiX docs) |

Each key record: `id`, `creation_time`, `created_by`, `user_name`, `roles`, `security_level`, `comment`, `expiration` (null = no expiry). **Secret key material is never returned** on get — only on generate.

**Lab totals (2026-09-20):** xsoar8 21 · xsiam 131 · xdr5 276 · agentix 4 keys.

---

## Generate an API Key

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/api_keys/generate` | `api_keys_generate_url(host)` |

**Request body:**

```json
{
  "request_data": {
    "roles": ["Investigator"],
    "security_level": "standard",
    "expiration": 1789902721000,
    "comment": "automation key"
  }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `roles` | Yes | Array of role names (must exist on tenant) |
| `security_level` | Yes | `standard` or `advanced` |
| `expiration` | No | Epoch ms; default ~1 week; max ~6 months |
| `comment` | No | Description |

**Response:** `{ "reply": { "id": <int>, "key": "<secret>" } }` — **`key` is shown once**; store immediately.

---

## Delete API Keys

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/api_keys/delete` | `api_keys_delete_url(host)` |

**Request body:**

```json
{
  "request_data": {
    "filters": [
      {"field": "id", "operator": "in", "value": [933]}
    ]
  }
}
```

**Response:** `{ "reply": { "update_count": <n> } }`

**Caution:** Do not delete the API key used for authentication. Filter by generated probe ID only in automation.

---

## Probe results (2026-09-20)

Full **generate → delete → verify gone** cycle on all platforms (probe keys deleted immediately; lab credential keys untouched).

| Platform | get_api_keys | generate | delete | total keys (tenant) |
| --- | --- | --- | --- | --- |
| xsoar8 | 200 ✓† | 200 | 200 (`update_count: 1`) | 21 |
| xsiam | 200 | 200 | 200 | 131 |
| xdr5 | 200 | 200 | 200 | 276 |
| agentix | 200 | 200 | 200 | 4 |

**Undocumented get path variants (all platforms):**

| Path | Result |
| --- | --- |
| `/public_api/v1/api_keys/get_api_keys` | **200** |
| `/public_api/v1/api_keys/get` | 500 |
| `/public_api/v1/api_keys/list` | 500 |

**Probe artifact:** `/tmp/api-keys-probe.json`

---

## Lab tenants

| Platform | Credentials (bay lab) |
| --- | --- |
| xsoar8 | `lab-xsoar-credentials.json` |
| xsiam | `lab-xsiam-credentials.json` |
| xdr5 | `lab-xdr-credentials.json` |
| agentix | `lab-agentix-credentials.json` |
