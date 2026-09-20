# Toolkit web API — master reference

Canonical map of **local REST routes** (`http://127.0.0.1:8770`), **CLI equivalents**, **UI location**, **tenant API paths**, and **platform support**.

Support legend (from [`platforms.py`](../../../cortex_ps_toolkit/platforms.py) `OPERATIONS` registry):

| Symbol | Meaning |
| --- | --- |
| **doc** | Documented / lab-verified on that platform |
| **exp** | Experimental compat path |
| **—** | Unsupported |

Platform columns: **6** = XSOAR 6, **8** = XSOAR 8, **XM** = XSIAM, **3** = XDR 3, **5** = XDR 5, **AX** = AgentiX.

Refresh matrix: `python3 -m cortex_ps_toolkit platforms list`

---

## Health & settings

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/health` | GET | — | (startup) | — | — | doc | doc | doc | doc | doc | doc |
| `/api/settings` | GET/PATCH | — | Settings panel | — | — | doc | doc | doc | doc | doc | doc |
| `/api/cache/status?profile=` | GET | `cache query` (scopes) | Profile context | — | — | doc | doc | doc | exp | exp | exp |

### `GET /api/settings`

```json
{
  "version": 1,
  "cache_ttl_seconds": 300,
  "max_inflight_per_host": 5,
  "max_inflight_global": 20
}
```

### `PATCH /api/settings`

Body may include any of: `cache_ttl_seconds`, `max_inflight_per_host`, `max_inflight_global` (all optional; minimum 1 for concurrency, 30 for TTL).

### `GET /api/cache/status?profile={slug}`

Returns per-scope staleness plus effective profile TTL and concurrency overrides:

```json
{
  "profile": "xsoar-japac-dev",
  "ttl_seconds": 300,
  "profile_ttl_seconds": null,
  "max_inflight_per_host": null,
  "max_inflight_global": null,
  "playbooks": { "refreshed_at": "…", "stale": false, "count": 587 },
  "scripts": { "…": "…" },
  "lists": { "…": "…" }
}
```

---

## Credentials

| Toolkit REST | Method | CLI | UI | Tenant API (validate) | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/credentials` | GET | `credentials list` | API Profiles grid | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials` | POST | — | Add profile modal | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials/{slug}` | GET/PUT/DELETE | `credentials show` / `remove` | Row actions | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials/import-lab` | POST | `credentials import-lab` | Toolbar | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials/purge-expired` | POST | `credentials purge-expired` | Toolbar | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials/{slug}/validate` | POST | — | Validate row | Platform-specific health/diagnostics | `credentials.validate` | doc | doc | doc | doc | doc | doc |
| `/api/credentials/{slug}/expiry` | POST | `credentials expiry set\|clear` | — | — | — | doc | doc | doc | doc | doc | doc |
| `/api/credentials/{slug}/verify-ssl` | POST | `credentials verify-ssl set` | — | — | — | doc | doc | doc | doc | doc | doc |

Detail: [`credentials.md`](credentials.md)

---

## Lists

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/lists?profile=` | GET | `lists list` | List Tools grid | — (cache) | `playbooks.list`¹ | doc | doc | exp | exp | exp | exp |
| `/api/lists/{list_id}?profile=` | GET | `lists show` | List viewer | `GET …/lists/download/{id}` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |
| `/api/lists/refresh` | POST | `lists refresh` | Refresh cache | `GET/POST …/lists` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |
| `/api/lists/copy/preview` | POST | `lists copy-preview` | Copy wizard | `POST …/lists/save` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |
| `/api/lists/copy` | POST | `lists copy` | Copy wizard | `POST …/lists/save` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |
| `/api/lists/delete/preview` | POST | `lists delete-preview` | Delete | `POST …/lists/delete` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |
| `/api/lists/delete` | POST | `lists delete` | Delete | `POST …/lists/delete` | `content.lists.manage` | doc | doc | exp | exp | exp | exp |

¹ Lists use the same cache/list pattern; operation id is `content.lists.manage`.

Path rules: [`../lists/README.md`](../lists/README.md). Detail: [`lists.md`](lists.md).

---

## Playbooks

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/playbooks?profile=` | GET | `playbooks list` | Playbook Tools grid | — (cache) | `playbooks.list` | doc | doc | doc | — | — | — |
| `/api/playbooks/refresh` | POST | `playbooks refresh` | Refresh (also scripts) | `POST …/playbook/search` | `cache.playbooks.refresh` | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/{id}/analysis` | GET | `playbooks analyze` | Analysis accordion | Cache bodies + script metadata | `playbooks.metrics` | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/presets` | GET | — | Analysis → Refactor preset picker | — | — | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/workflow` | POST | `scripts/benchmark_mfec_refactor.py` | — | `POST …/playbook/save/yaml` | `playbooks.refactor.extract_multi` | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/preview` | POST | `playbooks refactor-preview` | Analysis → Refactor | (preflight only) | `playbooks.refactor.extract_multi` | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/execute` | POST | `playbooks refactor` | Analysis → Run refactor (HTTP fallback) | `POST …/playbook/save/yaml` | `playbooks.refactor.extract_multi` | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/update-tasks/preview` | POST | `playbooks update-tasks-preview` | — | (preflight) | `playbooks.refactor.update_tasks` | doc | doc | doc | — | — | — |
| `/api/playbooks/refactor/update-tasks` | POST | `playbooks update-tasks` | — | `POST …/playbook/save/yaml` | `playbooks.refactor.update_tasks` | doc | doc | doc | — | — | — |
| `/api/playbooks/copy/preview` | POST | `playbooks copy-preview` | Copy selected | `POST …/playbook/save/yaml` or zip insert | `playbooks.copy` | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/copy` | POST | `playbooks copy` | Copy selected | same | `playbooks.copy` | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/copy-components/preview` | POST | `playbooks copy-components-preview` | Analysis → Copy components | scripts + playbooks save | `playbooks.copy` | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/copy-components` | POST | `playbooks copy-components` | Analysis → Copy components | same | `playbooks.copy` | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/delete/preview` | POST | `playbooks delete-preview` | Delete | `POST …/playbook/delete` | `playbooks.copy`² | doc | doc | doc | exp | exp | exp |
| `/api/playbooks/delete` | POST | `playbooks delete` | Delete | same | `playbooks.copy`² | doc | doc | doc | exp | exp | exp |

² Delete shares copy platform gates.

**Tenant path prefix:** XSOAR 6 uses legacy paths (no `/xsoar/public/v1`). XSOAR 8 uses `/xsoar/public/v1`. XSIAM/XDR/AgentiX use compat `/xsoar/public/v1/…` for search/save and `/public_api/v1/playbooks/*` for zip get/insert on copy.

Refactor wraps [`bay/playbook-utils`](../../../../bay/playbook-utils/AGENTS.md) (`extract-multi`, `update-playbook-tasks`).

Detail: [`playbooks.md`](playbooks.md)

---

## Scripts

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/scripts?profile=` | GET | `scripts list` | Script Tools grid | — (cache) | `cache.scripts.refresh` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/{script_id}?profile=` | GET | `scripts show` | Script viewer | automation load/get | `cache.scripts.refresh` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/refresh` | POST | `scripts refresh` | Refresh cache | `POST …/automation/search` | `cache.scripts.refresh` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/copy/preview` | POST | `scripts copy-preview` | Copy | save/load automation | `scripts.copy` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/copy` | POST | `scripts copy` | Copy | same | `scripts.copy` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/delete/preview` | POST | `scripts delete-preview` | Delete | automation delete | `scripts.copy` | doc | doc | doc | exp | exp | exp |
| `/api/scripts/delete` | POST | `scripts delete` | Delete | same | `scripts.copy` | doc | doc | doc | exp | exp | exp |

Detail: [`scripts.md`](scripts.md). CLI: `scripts describe --profile … --id …`.

---

## Integrations

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/integrations/configurations?profile=` | GET | `integrations list` | Definitions tab | `POST …/integration/search` | `cache.integrations.instances.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/definitions/{id}?profile=` | GET | `integrations show` | Definition viewer | `POST …/integration/search` | `cache.integrations.instances.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/instances/{id}?profile=` | GET | — | Instance viewer | `POST …/integration/search` | `cache.integrations.instances.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/commands?profile=` | GET | — | Commands tab | `GET …/settings/integration-commands` | `cache.integrations.commands.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/commands/{id}?profile=` | GET | — | Commands viewer | `GET …/settings/integration-commands` | `cache.integrations.commands.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/instances?profile=` | GET | — | Instances tab | `POST …/settings/integration/search` | `cache.integrations.instances.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/tenant-credentials?profile=` | GET | — | Tenant credentials tab | `POST …/settings/credentials` | `cache.credentials.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/packs?profile=` | GET | — | Installed packs tab | `GET …/contentpacks/metadata/installed` | `cache.contentpacks.refresh` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/refresh` | POST | `integrations refresh` | Refresh cache | All four above | (combined) | doc | doc | doc | exp | doc | doc |
| `/api/integrations/copy/preview` | POST | `integrations copy-preview` | Copy | `POST …/integration-conf/upload` | `integrations.copy` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/copy` | POST | `integrations copy` | Copy | same | `integrations.copy` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/delete/preview` | POST | `integrations delete-preview` | Delete | `POST …/integration-conf/delete` | `integrations.delete` | doc | doc | doc | exp | doc | doc |
| `/api/integrations/delete` | POST | `integrations delete` | Delete | same | `integrations.delete` | doc | doc | doc | exp | doc | doc |

WebSocket: `cache.refresh` scope `integrations`.

Lab probe: [`../../api-compat/integrations-probe.md`](../../api-compat/integrations-probe.md).

Detail: [`integrations.md`](integrations.md)

---

## Vault (local only)

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/vault/status` | GET | — | API Profiles / Vault | — | `vault.manage` | doc | doc | doc | doc | doc | doc |
| `/api/vault/init` | POST | — | Vault setup | — | `vault.manage` | doc | doc | doc | doc | doc | doc |
| `/api/vault/unlock` / `lock` | POST | — | Vault unlock | — | `vault.manage` | doc | doc | doc | doc | doc | doc |
| `/api/vault/wraps` | GET/POST | — | Passphrase slots | — | `vault.manage` | doc | doc | doc | doc | doc | doc |
| `/api/vault/wraps/revoke` | POST | — | Revoke slot by alias | — | `vault.manage` | doc | doc | doc | doc | doc | doc |
| `/api/vault/entries` | GET/POST | — | Stored entries | — | `vault.manage` | doc | doc | doc | doc | doc | doc |

Detail: [`vault.md`](vault.md), [`../../CREDENTIALS_VAULT.md`](../../CREDENTIALS_VAULT.md).

---

## XQL

| Toolkit REST | Method | CLI | UI | Tenant API | Operation | 6 | 8 | XM | 3 | 5 | AX |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/api/xql/run` | POST | `xql run` | XQL monitor embed | `POST /public_api/v1/xql/start_xql_query` (+ poll/stream) | `xql.run` | — | — | doc | doc | doc | exp |
| `/api/xql/presets/builtin` | GET | — | Preset picker | — | — | — | — | doc | doc | doc | exp |
| `/api/xql/presets/user` | GET/POST | — | User presets | — | — | — | — | doc | doc | doc | exp |
| `/api/xql/presets/user/{id}` | DELETE | — | Delete preset | — | — | — | — | doc | doc | doc | exp |

Detail: [`xql.md`](xql.md)

---

## Design content

Asset kinds: `layouts`, `classifiers`, `preprocess`, `incident-fields`, `incident-types`.

| Toolkit REST | Method | CLI | UI | Tenant API | Operation |
| --- | --- | --- | --- | --- | --- |
| `/api/profile/capabilities?profile=` | GET | — | Object Setup / Indicators / System Admin | Per-profile list/copy/delete flags | — |
| `/api/design-content/{asset}?profile=` | GET | `design-content list` | Object Setup grid | List/get per asset | `content.*.manage` |
| `/api/design-content/{asset}/{item_id}?profile=` | GET | `design-content show` | — | Same | — |
| `/api/design-content/refresh` | POST | `design-content refresh` | Refresh cache | Fetch all items | — |
| `/api/design-content/{asset}/copy/preview` | POST | `design-content copy-preview` | — | Bundle or direct POST | — |
| `/api/design-content/{asset}/copy` | POST | `design-content copy` | Copy selected | Bundle or direct POST | — |
| `/api/design-content/{asset}/delete/preview` | POST | `design-content delete-preview` | — | Platform-specific delete | — |
| `/api/design-content/{asset}/delete` | POST | `design-content delete` | Object Setup delete | Platform-specific delete | — |
| `/api/design-content/orchestrate` | POST | `design-content orchestrate` | Run ordered workflow | Ordered multi-asset copy | — |

Orchestrator order: incident-fields → layouts → incident-types → classifiers → preprocess (optional correlation rules via platform-admin).

`GET /api/cache/status` includes `design_content.{asset}` staleness for each kind.

---

## Platform admin (Object Setup correlation + Indicators + System Admin)

Sections: `correlation-rules` (Object Setup), `biocs` + `indicators` (Indicators), `rbac-*` + `api-keys` (System Admin).

| Toolkit REST | Method | CLI | UI | Tenant API |
| --- | --- | --- | --- | --- |
| `/api/platform-admin/{section}?profile=` | GET | `platform-admin list` | Grouped content grids | `/public_api/v1/...` |
| `/api/platform-admin/refresh` | POST | `platform-admin refresh` | Refresh buttons | Fetch section(s) |
| `/api/platform-admin/correlation-rules/copy/preview` | POST | — | Object Setup copy preview | Plan only |
| `/api/platform-admin/correlation-rules/copy` | POST | `platform-admin copy-correlation-rules` | Object Setup copy | `correlations/insert` |
| `/api/platform-admin/correlation-rules/delete/preview` | POST | — | Object Setup delete preview | Plan only |
| `/api/platform-admin/correlation-rules/delete` | POST | — | Object Setup delete | `correlations/delete` |
| `/api/platform-admin/biocs/copy/preview` | POST | — | Indicators copy preview | Plan only |
| `/api/platform-admin/biocs/copy` | POST | `platform-admin copy-biocs` | Indicators copy | `bioc/insert` |
| `/api/platform-admin/biocs/delete/preview` | POST | — | Indicators delete preview | Plan only |
| `/api/platform-admin/biocs/insert` | POST | `platform-admin insert-biocs` | — | `bioc/insert` |
| `/api/platform-admin/biocs/delete` | POST | `platform-admin delete-biocs` | Indicators delete | `bioc/delete` |
| `/api/platform-admin/indicators/copy/preview` | POST | — | Indicators copy preview | Plan only |
| `/api/platform-admin/indicators/copy` | POST | `platform-admin copy-indicators` | Indicators copy | Re-insert / XSOAR create |
| `/api/platform-admin/indicators/delete` | POST | — | Indicators delete | `indicators/delete` |
| `/api/platform-admin/api-keys/generate` | POST | — | System Admin generate | `api_keys/generate` |
| `/api/platform-admin/api-keys/delete` | POST | — | System Admin delete | `api_keys/delete` |

`GET /api/cache/status` includes `platform_admin.{section}` staleness.

---

## WebSocket

| Message | Direction | CLI | UI | Effect |
| --- | --- | --- | --- | --- |
| `cache.refresh` | client → server | `lists/playbooks/scripts refresh` | Refresh buttons | **Elective** background refresh (TTL skip); independent scopes run **in parallel** |
| `design_content.refresh` | client → server | `design-content refresh` | Design Content refresh | Background refresh; streams `job.progress` heartbeats (~30s) |
| `design_content.copy` | client → server | `design-content copy` | Copy selected | Long copy; heartbeats + step events |
| `design_content.orchestrate` | client → server | `design-content orchestrate` | Run ordered workflow | Multi-asset workflow; heartbeats + step events |
| `platform_admin.refresh` | client → server | `platform-admin refresh` | Indicators / System Admin refresh | Section or all; heartbeats |
| `platform_admin.correlation_copy` | client → server | `platform-admin copy-correlation-rules` | Object Setup copy | Long copy; heartbeats |
| `platform_admin.bioc_copy` | client → server | `platform-admin copy-biocs` | Indicators BIOC copy | Long copy; heartbeats |
| `platform_admin.indicator_copy` | client → server | `platform-admin copy-indicators` | Indicators IOC copy | Long copy; heartbeats |
| `design_content.delete` | client → server | `design-content delete` | Object Setup delete | Bulk delete; heartbeats |
| `platform_admin.correlation_delete` | client → server | `platform-admin delete-correlation-rules` | Object Setup delete | Correlation rule delete |
| `platform_admin.bioc_delete` | client → server | `platform-admin delete-biocs` | Indicators BIOC delete | BIOC delete |
| `platform_admin.indicator_delete` | client → server | `platform-admin delete-indicators` | Indicators IOC delete | Indicator delete |
| `cache.refresh` scope `integrations` | client → server | — | Integrations refresh | Elective refresh; integration sub-scopes parallelized |
| `cache.refresh` scope `all` | client → server | — | Full refresh | playbooks + scripts + lists + integrations (parallel where independent) |
| `playbooks.refactor.execute` | client → server | `playbooks refactor` | Analysis → Run refactor | Long-running extract-multi; streams `job.progress` |
| `playbooks.refactor.workflow` | client → server | benchmark script | — | Clear + multi-step preset; streams `job.progress` |
| `job.progress` | server → client | — | Toasts / refactor panel | Step events + ~30s heartbeats (`phase=heartbeat`, `in_flight`, `current`, `elapsed_seconds`) |
| `ops.log` | server → client | — | Ops log panel | Structured operation log stream |

HTTP `POST /api/*/refresh` routes use **required** refresh (always fetch). WebSocket refresh respects profile/global TTL.

Connect: `ws://127.0.0.1:8770/ws`

---

## Server & paths

```bash
python3 -m cortex_ps_toolkit serve --host 127.0.0.1 --port 8770
python3 -m cortex_ps_toolkit paths
python3 -m cortex_ps_toolkit platforms list --docs
```

OpenAPI archives (tenant APIs): [`../../../../ai/guidance-cache/cortex-openapi-index.md`](../../../../ai/guidance-cache/cortex-openapi-index.md)

---

## Maintenance

Update this file when adding routes in `cortex_ps_toolkit/server/app.py` or CLI subcommands in `cortex_ps_toolkit/cli.py`. Cross-check `platforms.OPERATIONS` and per-resource docs under `docs/api/toolkit/`.
