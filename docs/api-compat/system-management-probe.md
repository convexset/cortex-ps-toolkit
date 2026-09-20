# System management / RBAC API compatibility probe

Lab-verified **Get Users**, **Get Roles**, **Get User Groups**, and **Set a User Role** paths for Cortex cloud tenants, probed **2026-09-20** with API key authentication (`Authorization` + `x-xdr-auth-id`).

**Scope:** **xsoar8**, **xsiam**, **xdr5**, **agentix** only — not xsoar6 (no documented `/public_api/v1/rbac/*` on XSOAR 6 system-management docs).

**Helpers:** `cortex_ps_toolkit/core/paths.py` — `rbac_get_users_url()`, `rbac_get_roles_url()`, `rbac_get_user_group_url()`, `rbac_set_user_role_url()`.

**Related:** [api-keys-probe.md](api-keys-probe.md) (API key CRUD), [content-probe.md](content-probe.md) (design-time content), [integrations-probe.md](integrations-probe.md) (settings / packs), [../PLATFORMS.md](../PLATFORMS.md).

---

## Documentation sources

| Platform | System management docs |
| --- | --- |
| xsoar8 | [XSOAR 8 system management](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/system-management) |
| xsiam | [XSIAM system management](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/system-management) |
| xdr5 | [XDR 5 system management](https://cortex-docs.paloaltonetworks.com/xdr-5-api/cortex-platform/system-management) |
| agentix | [AgentiX system management](https://cortex-docs.paloaltonetworks.com/agentix-api/cortex-agentix/system-management) |

All four platforms share the same host-root public API prefix: **`/public_api/v1/rbac/*`**.

---

## Capability matrix

| Operation | xsoar8 | xsiam | xdr5 | agentix |
| --- | --- | --- | --- | --- |
| Get Users | ✓ | ✓ | ✓ | ✓ |
| Get Roles | ✓† | ✓† | ✓† | ✓† |
| Get User Groups | ✓‡ | ✓‡ | ✓‡ | ✓‡ |
| Set a User Role | ✓§ | ✓§ | ✓§ | ✓§ |

† **`role_names` is required in practice** — empty or omitted `role_names` → HTTP 500 (`role_names param is missing`). There is no “list all roles” call without names; derive distinct `role_name` values from **Get Users** first, then batch **Get Roles**.

‡ **`group_names` is required** — pass one or more group names (discover from user `groups` fields or tenant UI).

§ **Protected roles** (e.g. `Account Admin`) reject assignment via API (`Can not update users to Account Admin role.`). Idempotent re-set of an existing non-protected role returns HTTP 200 with `update_count: 0`.

---

## Get Users

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/rbac/get_users` | `rbac_get_users_url(host)` |

**Request body:** `{}` (empty JSON object is sufficient).

**Response:** `{ "reply": [ { "user_email", "user_first_name", "user_last_name", "role_name", "last_logged_in", "user_type", "groups", "scope" }, ... ] }`

**Lab counts (2026-09-20):** xsoar8 125 · xsiam 131 · xdr5 401 · agentix 363 users.

---

## Get Roles

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/rbac/get_roles` | `rbac_get_roles_url(host)` |

**Request body:**

```json
{
  "request_data": {
    "role_names": ["Investigator", "Account Admin"]
  }
}
```

**Response:** `{ "reply": [ ... ] }` — each top-level entry may be a **nested list** of role objects (flatten before use). Role object fields: `pretty_name`, `permissions`, `insert_time`, `update_time`, `created_by`, `description`, `groups`, `users`.

**Workflow to enumerate roles:**

1. `get_users` → collect distinct `role_name` values.
2. `get_roles` with `role_names` batched (lab used ≤20 names per call).

---

## Get User Groups

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/rbac/get_user_group` | `rbac_get_user_group_url(host)` |

**Request body:**

```json
{
  "request_data": {
    "group_names": ["SOC Users Group"]
  }
}
```

**Response:** `{ "reply": [ { "group_name", "pretty_name", "description", "insert_time", "update_time", "user_email", "source" }, ... ] }`

Note: API path is **`get_user_group`** (singular), docs title “Get User Groups”.

---

## Set a User Role

| Method | Path | Helper |
| --- | --- | --- |
| `POST` | `/public_api/v1/rbac/set_user_role` | `rbac_set_user_role_url(host)` |

**Request body (assign role):**

```json
{
  "request_data": {
    "user_emails": ["user@example.com"],
    "role_name": "Investigator"
  }
}
```

**Remove role:** send `"role_name": ""` (empty string) per docs.

**Response:** `{ "reply": { "update_count": "<n>" } }` — lab idempotent same-role calls returned `update_count: 0`.

**Caveats:**

- API key must have RBAC admin permissions (403 otherwise).
- Cannot assign users to **Account Admin** (and likely other top-level admin roles) via this endpoint.
- Prefer read-only verification in automation; role changes affect tenant access.

---

## Probe results (2026-09-20)

| Platform | get_users | get_roles | get_user_group | set_user_role (idempotent) |
| --- | --- | --- | --- | --- |
| xsoar8 | 200 (125 users) | 200 (3 roles†) | 200 | 200 (`update_count: 0`) |
| xsiam | 200 (131) | 200 (3) | 200 | 200 |
| xdr5 | 200 (401) | 200 (11) | 200 | 200 |
| agentix | 200 (363) | 200 (3) | 200 | 200 |

† Role count after flattening nested `reply` arrays; `role_names` batch size capped at 20 in probe.

**Probe artifact:** `/tmp/system-management-probe.json`

---

## Lab tenants

| Platform | Credentials (bay lab) |
| --- | --- |
| xsoar8 | `lab-xsoar-credentials.json` |
| xsiam | `lab-xsiam-credentials.json` |
| xdr5 | `lab-xdr-credentials.json` |
| agentix | `lab-agentix-credentials.json` |
