# Toolkit REST — Integrations

Cached integration definitions, instances, tenant credential **metadata**, installed content packs, and copy/delete of **custom integration definitions**.

## GET /api/integrations/configurations?profile={slug}

Cached integration **definitions** (from `integration/search` → `configurations[]`, indexed with instance counts).

**Tenant API:** `POST {host}/…/settings/integration/search` with `{}`.

**Operation:** `cache.integrations.instances.refresh`

**CLI:** `integrations list --profile {slug}` (definitions from instances cache)

**UI:** Integrations panel → **Definitions** tab (copy/delete actions).

## GET /api/integrations/definitions/{integration_id}?profile={slug}

Full integration **definition** for the web viewer: sanitized configuration JSON (without embedded script body) plus `script` and `script_language` fields.

Served from cache (`configuration_bodies`) when available; otherwise live `integration/search` + sanitize.

**UI:** Integrations panel → **Definitions** tab → double-click row or **View selected**.

## GET /api/integrations/instances/{instance_id}?profile={slug}

Full sanitized integration **instance** configuration (secrets stripped).

Served from cache (`instance_bodies`) when available; otherwise live `integration/search` + sanitize.

**UI:** Integrations panel → **Instances** tab → double-click row or **View selected**.

Response includes `parameters` (instance `data[]` with secret values stripped) separate from `configuration` metadata.

## GET /api/integrations/commands?profile={slug}

Cached integration command catalog (`data/cache/{cache_key}/integrations/commands/`). Each row is an integration with a `command_count` (metadata only — not full command argument schemas).

**Tenant API:** `GET {host}/settings/integration-commands` (XSOAR 6) or `{host}/xsoar/public/v1/settings/integration-commands` (XSOAR 8 / compat platforms).

**Operation:** `cache.integrations.commands.refresh`

**UI:** Integrations panel → **Commands** tab (after Instances).

## GET /api/integrations/commands/{integration_id}?profile={slug}

Full integration command catalog entry for the web viewer: metadata in `configuration`, command definitions in `commands`.

Served from cache (`integration_bodies`) when available; otherwise live `integration-commands` fetch.

**UI:** Integrations panel → **Commands** tab → double-click row or **View selected**.

## GET /api/integrations/instances?profile={slug}

Cached integration instances (secrets stripped before persist).

**Tenant API:** `POST {host}/…/settings/integration/search` with `{}`.

**Operation:** `cache.integrations.instances.refresh`

## GET /api/integrations/tenant-credentials?profile={slug}

Tenant credential objects — **metadata only** (`hasPassword`, no secret values).

**Tenant API:** `POST {host}/…/settings/credentials`.

**Operation:** `cache.credentials.refresh`

## GET /api/integrations/packs?profile={slug}

Installed content pack metadata.

**Tenant API:** `GET {host}/…/contentpacks/metadata/installed`.

**Operation:** `cache.contentpacks.refresh`

## POST /api/integrations/refresh

**Request:** `{ "profile": "psojapac-xsiam" }`

Refreshes all four scopes above.

**CLI:** `integrations refresh --profile {slug}`

**WebSocket:** send `{ "type": "cache.refresh", "profile": "…", "scope": "integrations" }`.

---

## POST /api/integrations/copy/preview

**Request:**

```json
{
  "source_profile": "personal-xsoar6",
  "target_profile": "xsoar-japac-dev",
  "integration_ids": ["MyCustomIntegration"],
  "overwrite": true,
  "stop_on_conflict": false
}
```

**Response:** plan with per-item `action` (`copy`, `update`, `skip`, `conflict`, `blocked`), `counts`, `would_abort`.

**Copy rules:** non-system, non-pack integrations with a script body in `integration/search`. Pack integrations must be installed on the target separately.

**CLI:** `integrations copy-preview --from-profile … --to-profile … --id … [--overwrite] [--stop-on-conflict]`

**Operation:** `integrations.copy`

## POST /api/integrations/copy

Execute copy plan. Uploads demisto-style YAML via `POST …/integration-conf/upload`.

After copy, the toolkit refreshes the target tenant integrations cache. The web UI triggers the same refresh before reloading grids. Per-item success toasts are published over WebSocket (5s auto-dismiss).

**CLI:** `integrations copy --from-profile … --to-profile … --id …`

**Tenant API (upload):**

| Platform | Path |
| --- | --- |
| **xsoar6** | `POST /settings/integration-conf/upload` |
| **xsoar8+** (web-app) | `POST /xsoar/settings/integration-conf/upload` |

---

## POST /api/integrations/delete/preview

**Request:**

```json
{
  "profile": "personal-xsoar6",
  "integration_ids": ["MyCustomIntegration"]
}
```

**Response:** plan with `warnings[]` when instances exist for the integration brand (`has_instance_warnings`, `instance_count`, `instance_names`). Instances do **not** block deletion.

**CLI:** `integrations delete-preview --profile … --id …`

**Operation:** `integrations.delete`

## POST /api/integrations/delete

Execute delete. Posts the full ModuleConfiguration document to `POST …/integration-conf/delete`.

**CLI:** `integrations delete --profile … --id …`

After delete, the toolkit refreshes the integrations cache from the tenant (definitions, instances, commands catalog). The web UI triggers the same refresh before reloading grids.

**Tenant API (delete):**

| Platform | Path |
| --- | --- |
| **xsoar6** | `POST /settings/integration-conf/delete` |
| **xsoar8+** (web-app) | `POST /xsoar/settings/integration-conf/delete` |

Do **not** use `DELETE …/settings/integration/{instance_id}` for definition removal.

---

## Platform support

| Platform | Cache | Copy | Delete |
| --- | --- | --- | --- |
| xsoar6 | doc | doc | doc |
| xsoar8 | doc | doc | doc |
| xsiam | doc | doc | doc |
| xdr5 | doc | doc | doc |
| agentix | doc | doc | doc |
| xdr3 | exp | exp | exp |

Lab verification: [`../../api-compat/integrations-probe.md`](../../api-compat/integrations-probe.md).

Master table: [`WEB-API.md`](WEB-API.md)
