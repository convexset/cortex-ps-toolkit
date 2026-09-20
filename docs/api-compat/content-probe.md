# Design-time content API compatibility probe

Lab-verified **read all / read one / write one / delete one** paths for Cortex design-time content, probed **2026-09-20** with API key authentication (`Authorization` + `x-xdr-auth-id` on cloud tenants).

**Helpers:** `cortex_ps_toolkit/core/paths.py` — `xsoar_shaped_url()` for public v1 compat paths; `xsoar_webapp_url()` and asset-specific helpers for host-root web-app routes.

**Related:** [integrations-probe.md](integrations-probe.md) (settings / content packs), [../PLATFORMS.md](../PLATFORMS.md) (path substitution rules).

---

## Stock take (2026-09-20)

Cross-tenant design-time content management is **feasible externally** for most XSOAR-shaped assets. Implementation lives in `cortex_ps_toolkit/core/paths.py` (URL helpers) and this document (capability matrix).

### Three API surfaces

| Surface | Prefix | Auth (lab) | Use for |
| --- | --- | --- | --- |
| **Public v1 (shaped)** | `/xsoar/public/v1/...` (cloud); legacy root (xsoar6) | API key (+ `x-xdr-auth-id` on cloud) | Fields, types (write), bundle import, VC, indicators, dashboards |
| **XSOAR web-app (host root)** | `/xsoar/...` (cloud); legacy root (xsoar6) | Same API key | List/delete types; list classifiers & preprocess; delete fields/layouts |
| **Cortex UI web-app** | `/api/webapp/...` | **Session only** (API key → 500) | Parsing rules, XDM/data-model rules, layout grids — UI capture targets |

### What works today (external API key)

| Category | Full CRUD | Read + write + partial delete | Read only | Not on API key |
| --- | --- | --- | --- | --- |
| **XSOAR content** | Incident fields, incident types, layouts (read all) | Layouts (delete x6/x8; write via bundle), classifiers/preprocess (write bundle; delete x6 only) | VC catalog | `/api/webapp/*` |
| **Cortex Platform** | Correlation rules, IOC delete, RBAC (xsiam, xdr5, agentix; xsoar8 RBAC) | Indicators (shaped search/create on all) | — | agentix public IOC/correlation 402 in lab |
| **Ingestion / XDM** | — | — | — | Parsing rules (xsiam/xdr/agentix UI); XDM rules (xsiam/agentix UI) — session auth |

### Path helpers shipped

| Helper | Asset |
| --- | --- |
| `incidentfields_list_url`, `incidentfield_write_url`, `incidentfield_delete_url` | Incident fields |
| `incidenttype_list_url`, `incidenttype_write_url`, `incidenttype_delete_url` | Incident types |
| `classifier_search_url` | Classifiers / mappers |
| `preprocess_rules_list_url` | Preprocess rules |
| `layouts_list_url`, `layout_get_url`, `layout_delete_url` | Layouts |
| `content_bundle_import_url`, `content_bundle_export_url` | Content bundle |
| `vc_uncommitted_url` | VC catalog |
| `parsing_rule_files_*_get_url`, `xdm_mappings_files_*_get_url` | Parsing / XDM (URLs only — **not yet callable** with API key) |
| `indicators_get_url`, `indicators_insert_url`, `indicators_delete_url` | IOCs (XSIAM / XDR / AgentiX public API) |
| `rbac_get_users_url`, `rbac_get_roles_url`, `rbac_get_user_group_url`, `rbac_set_user_role_url` | User / RBAC management — see [system-management-probe.md](system-management-probe.md) |
| `api_keys_get_url`, `api_keys_generate_url`, `api_keys_delete_url` | API key management — see [api-keys-probe.md](api-keys-probe.md) |

### Recommended copy order

Fields → layouts (bundle) → incident types → classifiers/mappers → preprocess rules → correlation rules (xsiam/xdr5). Parsing rules and XDM mappings remain **out of scope** until session auth or a public API is found.

### Probe artifacts

`/tmp/api-feasibility-probe.json`, `/tmp/incidenttype-delete-probe.json`, `/tmp/classifier-preprocess-read-probe.json`, `/tmp/parsing-xdm-webapp-probe.json`, `/tmp/bundle-write-all-platforms.json`, `/tmp/x6-import-final-probe.json`, and others listed at the bottom of this doc.

**Bundle/import validation (2026-09-20):** layout (`layoutscontainer-*`), classifier (`classifier-*`), and preprocess (`preprocessrule-{uuid}-*`) write via `POST /content/bundle` verified on **xsoar6, xsoar8, xsiam, xdr5, agentix**. xsoar6 direct import paths also verified (`/layouts/import`, `/classifier/import`, `/preprocess/rule`). Implemented in `cortex_ps_toolkit/design_content/`.

---

## Two API surfaces (detail)

| Surface | Prefix | Use for |
| --- | --- | --- |
| **Public v1 (shaped)** | `/xsoar/public/v1/...` on cloud; legacy root on XSOAR 6 | Most documented CRUD (`incidentfields`, `POST /incidentfield`, `POST /incidenttype`, bundle import, VC) |
| **Web-app (host root)** | `/xsoar/...` on cloud; legacy root on XSOAR 6 | UI-backed routes **not** exposed on public v1 — list incident types, classifiers/mappers, preprocess rules; delete fields/types/layouts |
| **Cortex UI web-app** | `/api/webapp/...` | Data Management UI — parsing rules, XDM mappings (session auth required in lab) |

**Status codes:** `303` on shaped paths usually means “internal route, not public API”. `500` on `/api/webapp/*` with API key means session-only UI layer.

Path routing for shaped endpoints uses `xsoar_shaped_path()` (same rules as integrations probe). Web-app paths use `xsoar_webapp_path()`.

---

## Summary matrix

Legend: **✓** lab-verified · **filter** no GET-by-id; filter list · **VC** version-control catalog only · **bundle** gzip tar via `POST /content/bundle` · **—** not available externally · **402** license/RBAC block

| Asset | Op | xsoar6 | xsoar8 | xsiam | xdr5 | agentix |
| --- | --- | --- | --- | --- | --- | --- |
| **Incident fields** | read all | ✓ | ✓ | ✓ | ✓ | ✓ |
| | read one | filter | filter | filter | filter | filter |
| | write one | ✓ | ✓ | ✓ | ✓ | ✓ |
| | delete one | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Incident types** | read all | ✓ | ✓ | ✓ | ✓ | ✓ |
| | read one | filter | filter | filter | filter | filter |
| | write one | ✓ | ✓ | ✓ | ✓ | ✓ |
| | delete one | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Layouts** | read all | ✓ | ✓ | ✓ | ✓ | ✓ |
| | read one | ✓ | ✓ | filter/list | filter/list | filter/list |
| | write one | import/bundle | bundle | bundle | bundle | bundle |
| | delete one | ✓ | ✓ | — | — | — |
| **Classifiers / mappers** | read all | ✓ | ✓ | ✓ | ✓ | ✓ |
| | read one | filter | filter | filter | filter | filter |
| | write one | import/bundle | bundle | bundle | bundle | bundle |
| | delete one | ✓ | — | — | — | — |
| **Preprocess rules** | read all | ✓ | ✓ | ✓‡ | ✓‡ | ✓‡ |
| | read one | filter | filter | filter | filter | filter |
| | write one | ✓/bundle | bundle | bundle | bundle | bundle |
| | delete one | ✓ | — | — | — | — |
| **Content bundle** | export (read) | ✓ | — | — | — | — |
| | import (write) | ✓ | ✓ | ✓ | ✓ | ✓ |
| **VC uncommitted** | read catalog | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Correlation rules** | read all | — | — | ✓ | ✓ | 402¶ |
| | read one | — | — | filter | filter | 402¶ |
| | write one | — | — | ✓ | ✓ | 402¶ |
| | delete one | — | — | ✓ | ✓ | 402¶ |
| **Indicators** | read all | ✓ | ✓ | ✓ | ✓ | ✓ |
| | write one | ✓ | ✓ | ✓† | ✓† | 402¶ |
| | delete one | whitelist‡ | batch‡ | ✓ | ✓ | 402¶ |
| **Parsing rules** | read all | N/A | N/A | UI§ | UI§ | UI§ |
| | read one | N/A | N/A | UI§ | UI§ | UI§ |
| **Data model (XDM) rules** | read all | N/A | N/A | UI§ | N/A | UI§ |
| | read one | N/A | N/A | UI§ | N/A | UI§ |

§ **Parsing rules** apply to **XSIAM, XDR, AgentiX** only. **Data model (XDM) rules** apply to **XSIAM and AgentiX** only. UI paths (`/api/webapp/...`) return **500** with API key (2026-09-20); **xsoar6/xsoar8** are N/A (not XSIAM/XDR data-management tenants).

¶ **AgentiX** documents the same `/public_api/v1/correlations/*` and `/public_api/v1/indicators/*` APIs as XSIAM/XDR; lab tenant returns **402** (inactive license). UI grid `POST /api/webapp/get_data?table_name=CORRELATION_RULES` also **500** with API key — prefer documented public API when licensed.

† **xsiam/xdr5** IOC write/delete via `/public_api/v1/indicators/{insert,delete}` (verified insert→delete cycle). Shaped `POST /indicator/create` also works on all platforms.

‡ **xsoar6/xsoar8** delete via shaped `POST /indicators/batchDelete` (xsoar8: `/xsoar/public/v1/indicators/batchDelete`). Lab: **`ids` only → 500**; **`ids` + `filter.query: id:"{id}"` → 200** and indicator removed. XSIAM-style `POST /public_api/v1/indicators/delete` on xsoar6 returns SPA HTML; on xsoar8 returns **402** (inactive XSIAM license). xsoar6 doc path `POST /indicator-whitelist` → **405**.

‡ Preprocess list endpoint returns HTTP 200 on all cloud platforms; lab **xsiam / xdr5 / agentix** tenants had **no preprocess rules** (`null` JSON body). **xsoar8** returned a JSON array (`11` rules).

**xdr3:** Not probed; treat as **xdr5** per `paths.py` assumption until a lab tenant proves otherwise.

---

## Incident fields

Includes custom incident, evidence, and indicator fields — all returned by `GET /incidentfields` (filter client-side or by query params where supported).

### read all

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/incidentfields` |
| xsoar8, xsiam, xdr5, agentix | `GET` | `/xsoar/public/v1/incidentfields` |

Helper: `incidentfields_list_url(host, platform)`.

Evidence / indicator subsets: same endpoint; filter on `id` prefix (`evidence_*`, `indicator_*`) or `type` where present.

### read one

No reliable GET-by-id on cloud. **Filter the list** by `id` or `cliName`.

### write one

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| all | `POST` | shaped `/incidentfield` | Full field JSON object |

Helper: `incidentfield_write_url(host, platform)`.

Note: response is often the **full field list**, not just the created/updated field.

Alternative on **xsoar6** only: `POST /incidentfields/import` (multipart array).

### delete one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `DELETE` | `/incidentfield/{id}` |
| xsoar8, xsiam, xdr5, agentix | `DELETE` | `/xsoar/incidentfield/{id}` (host root, **not** public v1) |

Helper: `incidentfield_delete_url(host, platform, field_id)`.

**Does not work:** shaped `DELETE /xsoar/public/v1/incidentfield/{id}` → 303 on cloud; `POST /settings/fields/delete` → HTML/500 no-op.

---

## Incident types

### read all

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/incidenttype` |
| xsoar8, xsiam, xdr5, agentix | `GET` | `/xsoar/incidenttype` (host root) |

Helper: `incidenttype_list_url(host, platform)`.

**Does not work on cloud:** shaped `GET /xsoar/public/v1/incidenttype` → 405.

### read one

No GET-by-id/name on any platform (303/500). **Filter the list**; `id` is typically the display name string (e.g. `"AAAA - Test Incident Type"`).

### write one

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| all | `POST` | shaped `/incidenttype` | Incident type JSON (`id`, `name`, `layout`, `playbookId`, …) |

Helper: `incidenttype_write_url(host, platform)`.

Alternative on **xsoar6** only: `POST /incidenttypes/import` (multipart).

### delete one

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsoar6 | `POST` | `/incidenttype/delete` | `{"id": "<incident-type-id>"}` |
| xsoar8, xsiam, xdr5, agentix | `POST` | `/xsoar/incidenttype/delete` | `{"id": "<incident-type-id>"}` |

Helper: `incidenttype_delete_url(host, platform)`.

Response: `{}` with HTTP 200. Verify with follow-up list GET.

**Does not work:** shaped `POST /xsoar/public/v1/incidenttype/delete` → 303; `DELETE /xsoar/incidenttype/{id}` → 303; root `POST /incidenttype/delete` without `/xsoar` on cloud → 500.

---

## Layouts

### read all

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/layouts` |
| xsoar8, xsiam, xdr5, agentix | `GET` | `/xsoar/layouts` |

Helper: `layouts_list_url(host, platform)`.

Response: JSON **array** of layout objects (includes `id`, `name`, `details`, `detailsV2`, …). Lab counts (2026-09-20): xsoar6 `41`, xsoar8 `198`, xsiam `195`, xdr5 `16`, agentix `57`.

**Also tried (do not use):**

| Path | xsoar6 | cloud |
| --- | --- | --- |
| `GET /setting/layouts` | 303 | 500 (root) or 303 (`/xsoar/setting/layouts`) |
| `GET /settings/layouts` | 303 | 500 |
| shaped `GET /xsoar/public/v1/layouts` | — | 303 |
| root `GET /layouts` (no `/xsoar`) | ✓ (xsoar6) | 500 |

VC catalog remains useful for uncommitted filenames but is no longer required for list-all on cloud.

### read one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/layout/{id}` |
| cloud | `GET` | `/xsoar/layout/{id}` **or filter list** from `GET /xsoar/layouts` |

Helper: `layout_get_url(host, platform, layout_id)`.

URL-encode `id` when it contains spaces. The list endpoint returns full layout bodies — filtering by `id`/`name` may be enough without a separate GET.

### write one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `POST` | `/layouts/import` (multipart) |
| all cloud | `POST` | shaped `/content/bundle` (gzip tar with layout JSON under pack layout) |

Per-item `POST /layouts/import` → 303 on cloud.

### delete one

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsoar6 | `POST` | `/layout/{id}/remove` | `{}` or empty |
| xsoar8 | `POST` | `/xsoar/layout/{id}/remove` | `{}` |

Helper: `layout_delete_url(host, platform, layout_id)`.

**Does not work on cloud:** root `POST /layout/{id}/remove` (no `/xsoar`) → 500; shaped paths → 303. **xsiam / xdr5 / agentix:** not verified — shaped delete returns 303.

---

## Classifiers and mappers

Includes classifiers (`type`: `classification`) and incoming mappers (`type`: `mapping-incoming`) in one list.

### read all

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsoar6 | `POST` | `/classifier/search` | `{}` or search filter JSON |
| xsoar8, xsiam, xdr5, agentix | `POST` | `/xsoar/classifier/search` | `{}` or search filter JSON |

Helper: `classifier_search_url(host, platform)`.

Response: `{"total": N, "classifiers": […]}` — each item includes `id`, `name`, `type`, mapping/classification fields, pack metadata.

**Does not work on cloud:** root `POST /classifier/search` (no `/xsoar`) → 500; shaped `POST /xsoar/public/v1/classifier/search` → 303. On **xsoar6**, `POST /xsoar/classifier/search` returns SPA HTML (false positive 200).

Lab counts (2026-09-20): xsoar6 `11`, xsoar8 `193`, xsiam `230`, xdr5 `3`, agentix `44`.

### read one

Filter `classifiers` array from search response by `id` or `name`. VC catalog remains useful for filenames when preparing bundles.

### write one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `POST` | `/classifier/import` (multipart) |
| cloud | `POST` | shaped `/content/bundle` |

### delete one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `DELETE` | `/classifier/{id}` |
| cloud | — | shaped delete → 303 |

---

## Preprocess rules

### read all

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/preprocess/rules` |
| xsoar8, xsiam, xdr5, agentix | `GET` | `/xsoar/preprocess/rules` |

Helper: `preprocess_rules_list_url(host, platform)`.

Response: JSON **array** of rule objects when rules exist; JSON **`null`** when the tenant has none (empty xsoar6 lab tenant before 2026-09-20; xsiam/xdr5/agentix lab tenants). Re-probed **xsoar6** with one rule: `GET /preprocess/rules` → `list[1]` (`Close all with type AAAA - Empty Incident`). xsoar8 lab returned `11` rules.

**Does not work on cloud:** root `GET /preprocess/rules` → 500; shaped `GET /xsoar/public/v1/preprocess/rules` → 303. On **xsoar6**, `GET /xsoar/preprocess/rules` returns SPA HTML (false positive 200).

### read one

Filter the array by rule `id` or `name`. When the list endpoint returns `null`, fall back to VC (`type`: `preprocessrule`) for inventory metadata.

### write one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `POST` | `/preprocess/rule` |
| cloud | `POST` | shaped `/content/bundle` |

Direct `POST /preprocess/rule` → 303 on cloud.

### delete one

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `DELETE` | `/preprocess/rule/{id}` |
| cloud | — | shaped delete → 303 |

---

## Content bundle

### export (read all)

| Platform | Method | Path |
| --- | --- | --- |
| xsoar6 | `GET` | `/content/bundle` → gzip tar stream |
| cloud | — | 405 |

Helper: `content_bundle_export_url(host, platform)`.

### import (write)

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| all | `POST` | shaped `/content/bundle` | multipart field `file` = gzip tar |

Helper: `content_bundle_import_url(host, platform)`.

Primary cross-tenant write path for layouts, classifiers, preprocess on cloud.

---

## Version-control catalog

### read all (metadata)

| Platform | Method | Path |
| --- | --- | --- |
| all | `GET` | shaped `/vc/changes/uncommitted` |

Helper: `vc_uncommitted_url(host, platform)`.

Returns JSON array of `{name, type, filename, action, when, authorName, …}` — **no asset JSON bodies**. Use for inventory and resolving filenames before bundle export from XSOAR 6 or targeted GET on xsoar6/xsoar8.

---

## Correlation rules

**Platforms:** XSIAM, XDR 5.x, AgentiX (not xsoar6 / xsoar8).

Documented public API base: `/public_api/v1/correlations` ([XSIAM](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/correlation-rules), [XDR 5](https://cortex-docs.paloaltonetworks.com/xdr-5-api/cortex-platform/correlation-rules), [AgentiX](https://cortex-docs.paloaltonetworks.com/agentix-api/cortex-agentix/correlation-rules)). AgentiX UI also calls `POST /api/webapp/get_data?type=grid&table_name=CORRELATION_RULES` — use the **public API** when possible.

### read all

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/correlations/get` | `{"request_data": {"search_from": 0, "search_to": 100, "extended_view": true}}` |

Response (top-level): `{objects_count, objects[], objects_type}`. Lab: xsiam/xdr5 returned 100+ rules.

### read one

`POST /public_api/v1/correlations/get` with `request_data.filters`:

```json
{"field": "name", "operator": "EQ", "value": "<rule name>"}
```

Lab-verified: returns `objects_count: 1` for a known name.

### write one

| Platform | Method | Path |
| --- | --- | --- |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/correlations/insert` |

Body: `{"request_data": [<rule object>]}` — clone an existing rule and change `name` / `alert_name`; strip read-only fields (`rule_id`, `insert_time`, `modify_time`, `created_by`, `hits`). Response: `{added_objects, updated_objects, errors}`.

Lab-verified insert+delete cycle on xsiam and xdr5 (2026-09-20).

### delete one

| Platform | Method | Path |
| --- | --- | --- |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/correlations/delete` |

Body:

```json
{
  "request_data": {
    "filters": [{"field": "name", "operator": "EQ", "value": "<rule name>"}]
  }
}
```

Response: `{objects_count, objects: [<deleted rule ids>]}`. Lab-verified: deleted cloned probe rule (`objects_count: 1`); follow-up get filter returns `objects_count: 0`.

### agentix lab note

All `/public_api/v1/correlations/*` calls return **402** (`License is inactive…`) on the lab AgentiX tenant. Documented API shape matches XSIAM/XDR; enable correlation-rules license to probe further.

---

## BIOCs

**Platforms:** XSIAM, XDR 5.x (not xsoar6 / xsoar8). AgentiX documents the same API; lab may return **402** without license.

Documented public API base: `/public_api/v1/bioc` ([XSIAM BIOCs](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/biocs), [XDR 5 BIOCs](https://cortex-docs.paloaltonetworks.com/xdr-5-api/cortex-platform/biocs)).

Helpers: `biocs_get_url(host)`, `biocs_insert_url(host)`, `biocs_delete_url(host)`.

### read all

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsiam, xdr5 | `POST` | `/public_api/v1/bioc/get` | `{"request_data": {"search_from": 0, "search_to": 100, "extended_view": true}}` |

Response: `{objects_count, objects[], objects_type}`. Filters are **AND**-combined (OR not supported).

### read one

`POST /public_api/v1/bioc/get` with filter:

```json
{"field": "name", "operator": "EQ", "value": "<bioc name>"}
```

### write one (insert or update)

| Platform | Method | Path |
| --- | --- | --- |
| xsiam, xdr5 | `POST` | `/public_api/v1/bioc/insert` |

Body: `{"request_data": [<bioc object>]}` — writable fields include `name`, `type`, `severity`, `comment`, `status`, `is_xql`, `indicator`, MITRE fields, optional `rule_id`. Strip `rule_id` when cloning across tenants. Response: `{added_objects, updated_objects, errors}`.

### delete one

| Platform | Method | Path |
| --- | --- | --- |
| xsiam, xdr5 | `POST` | `/public_api/v1/bioc/delete` |

Body:

```json
{
  "request_data": {
    "filters": [{"field": "name", "operator": "EQ", "value": "<bioc name>"}]
  }
}
```

Filter fields: `name`, `severity`, `type`, `is_xql`, `comment`, `status`, `indicator`, MITRE fields. Response: `{objects_count, objects: [<deleted rule ids>]}`.

Toolkit: Platform Admin section `biocs`; CLI `platform-admin insert-biocs` / `delete-biocs`; REST `/api/platform-admin/biocs/{insert,delete}`.

---

## Parsing rules (XSIAM, XDR, AgentiX)

User-defined and system (default) parsing rule files in the Data Management UI.

### read all (UI endpoints — not yet working with API key)

| Ruleset | Method | Path | Helper |
| --- | --- | --- | --- |
| User defined | `POST` | `/api/webapp/ingestion/xql/rule_files/user/get` | `parsing_rule_files_user_get_url(host)` |
| System / default | `POST` | `/api/webapp/ingestion/xql/rule_files/system/get` | `parsing_rule_files_system_get_url(host)` |

**Platforms:** **XSIAM, XDR, AgentiX** only (not xsoar6 / xsoar8).

**Probe results (2026-09-20):** POST with `{}` and several UI-style payloads on **xsiam, xdr5, agentix** → **HTTP 500** (waitress internal error). **xsoar6/xsoar8** → N/A (not probed as ingestion tenants).

Same pattern as `/api/webapp/get_data?table_name=LAYOUTS` (layout grid): route exists in the UI but **requires browser session**, not standard API key auth.

**Next steps:** capture exact request body from browser DevTools while opening Parsing Rules editor; retry with session cookies, or locate a `/public_api/v1/...` equivalent (none in XSIAM Platform OpenAPI as of 2026-09-20).

### read one / write one / delete one

Not probed — blocked until list endpoint works externally. Content packs ship parsing rules as files under pack `ParsingRules/` (demisto-content); tenant copy may require UI export, pack upload, or future public API.

---

## Data model rules / XDM mappings (XSIAM, AgentiX)

User-defined and system XDM mapping files (modeling / data model rules in the UI).

### read all (UI endpoints — not yet working with API key)

| Ruleset | Method | Path | Helper |
| --- | --- | --- | --- |
| User defined | `POST` | `/api/webapp/xdm/xql/mappings_files/user/get` | `xdm_mappings_files_user_get_url(host)` |
| System | `POST` | `/api/webapp/xdm/xql/mappings_files/system/get` | `xdm_mappings_files_system_get_url(host)` |

**Platforms:** **XSIAM and AgentiX** only (not XDR, xsoar6, xsoar8).

**Probe results (2026-09-20):** **500** on xsiam/agentix with API key (same session-auth pattern as parsing rules UI).

---

## Indicators

Two delete surfaces exist depending on platform:

| Platform | Delete API | Docs |
| --- | --- | --- |
| xsoar6 | `POST /indicator-whitelist` | [XSOAR 6 indicators](https://cortex-docs.paloaltonetworks.com/xsoar-6-api/cortex-xsoar-6.x-apis/indicators#post-indicator-whitelist) |
| xsoar8 | shaped `POST /indicators/batchDelete` | [XSOAR 8 batchDelete](https://cortex-docs.paloaltonetworks.com/xsoar-8-api/cortex-xsoar-8.x-apis/indicators#post-xsoar-public-v1-indicators-batchdelete) |
| xsiam, xdr5, agentix | `POST /public_api/v1/indicators/delete` | [XSIAM IOCs](https://cortex-docs.paloaltonetworks.com/xsiam-api/cortex-platform/iocs#post-public_api-v1-indicators-delete), [XDR 5 IOCs](https://cortex-docs.paloaltonetworks.com/xdr-5-api/cortex-platform/iocs#post-public_api-v1-indicators-delete) |

### read all

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| all | `POST` | shaped `/indicators/search` | search filter JSON |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/indicators/get` | `indicators_get_url(host)` |

### write one

| Platform | Method | Path |
| --- | --- | --- |
| all | `POST` | shaped `/indicator/create` |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/indicators/insert` | `indicators_insert_url(host)` |

**Insert payload (public API):** array under `request_data`. Allowed fields: `indicator`, `type` (`HASH`, `IP`, `PATH`, `DOMAIN_NAME`, `FILENAME`, `MIXED`), `severity`, `expiration_date`, `default_expiration_enabled`, `comment`, `reputation`, `reliability`, optional `rule_id`. Strip read-only fields from a cloned `get` response before insert: `creation_time`, `modification_time`, `status`, `source`, `number_of_issues`.

### delete one

| Platform | Method | Path | Body |
| --- | --- | --- | --- |
| xsoar6 | `POST` | `/indicators/batchDelete` | see batchDelete payload below |
| xsoar8 | `POST` | shaped `/indicators/batchDelete` | see batchDelete payload below |
| xsiam, xdr5, agentix | `POST` | `/public_api/v1/indicators/delete` | `indicators_delete_url(host)` |

**Delete payload (XSOAR 6/8 batchDelete):**

```json
{
  "ids": ["114"],
  "doNotWhitelist": true,
  "all": false,
  "filter": {
    "query": "id:\"114\"",
    "size": 5
  }
}
```

Helper: `indicators_batch_delete_url(host, platform)`. **`ids` alone returns HTTP 500** on lab xsoar6/xsoar8; include the matching `id:"…"` filter query. Response field is spelled `uppdated` (typo in API). Filter-only or `value:"…"` filter returns 200 but deletes nothing.

**Delete payload (public API):**

```json
{
  "request_data": {
    "filters": [
      {"field": "indicator", "operator": "EQ", "value": "evil.example.com"}
    ]
  }
}
```

Filter fields: `indicator`, `type`, `severity`, `expiration_date`, `default_expiration_enabled`, `comment`, `reputation`, `reliability`. Operators: `EQ`, `NEQ`, `IN`, `GTE`, `LTE`. Filters are **AND**-combined.

**Response:** `{"objects_count": 1, "objects": [<rule_id>]}` — `objects` holds deleted IOC rule IDs.

### Probe results (2026-09-20)

| Platform | get | insert | delete | insert→delete cycle |
| --- | --- | --- | --- | --- |
| xsiam | 200 | 200 (`added_objects`) | 200 filter (`objects_count: 1`) | ✓ |
| xdr5 | 200 | 200 | 200 filter | ✓ |
| xsoar6 | shaped search | shaped create | batchDelete ids+id filter → 200 | ✓ |
| xsoar8 | shaped search | shaped create | batchDelete ids+id filter → 200 | ✓ |
| agentix | 402 | 402 | 402 | — (inactive license) |
| xsoar6/xsoar8 | — | — | public_api delete → HTML / 402 | — |
| xsoar6/xsoar8 | — | — | batchDelete ids-only → **500** | — |

Clone-from-get insert initially failed with **400** until read-only metadata fields were stripped; allowed-field-only payload succeeded on both xsiam and xdr5.

Probe artifacts: `/tmp/indicators-delete-probe.json` (xsiam/xdr5), `/tmp/xsoar-indicator-delete-probe.json` (xsoar6/xsoar8), `/tmp/iocs-biocs-lab-probe.json` (all lab tenants — IOC/BIOC cycles).

---

## Copy workflow (recommended)

1. **Source (xsoar6):** `GET /content/bundle` + direct list APIs (`/incidentfields`, `/incidenttype`, `/layouts`, classifier search, preprocess rules).
2. **Target (cloud):** write fields/types via shaped POST; write layouts/classifiers/preprocess via **bundle import**; read back types via `GET /xsoar/incidenttype`, classifiers via `POST /xsoar/classifier/search`, preprocess via `GET /xsoar/preprocess/rules`; VC for filenames.
3. **Cleanup (cloud):** delete fields `DELETE /xsoar/incidentfield/{id}`; types `POST /xsoar/incidenttype/delete`; layouts `POST /xsoar/layout/{id}/remove` (xsoar8 verified).
4. **Correlation rules (xsiam/xdr5):** native `/public_api/v1/correlations/*` CRUD.
5. **BIOCs (xsiam/xdr5):** native `/public_api/v1/bioc/{get,insert,delete}` — filter delete by `name` (EQ).
6. **IOCs (xsiam/xdr5):** native `/public_api/v1/indicators/{get,insert,delete}` — filter delete by `rule_id` or `indicator`.
7. **IOCs (xsoar6/xsoar8):** shaped `POST /indicators/batchDelete` with **`ids` + `filter.query: id:"…"`** — do not use Cortex Platform `/public_api/v1/indicators/delete`.

---

## Lab tenants and probe artifacts

| Platform | Credentials (bay lab) |
| --- | --- |
| xsoar6 | `personal-xsoar6-credentials.json` |
| xsoar8 | `lab-xsoar-credentials.json` |
| xsiam | `lab-xsiam-credentials.json` |
| xdr5 | `lab-xdr-credentials.json` |
| agentix | `lab-agentix-credentials.json` |

Raw probe JSON (local): `/tmp/api-feasibility-probe.json`, `/tmp/api-feasibility-cloud-probe.json`, `/tmp/incidentfield-xsoar-delete-probe.json`, `/tmp/incidenttype-read-probe.json`, `/tmp/incidenttype-delete-probe.json`, `/tmp/layout-delete-probe2.json`, `/tmp/layouts-list-probe.json`, `/tmp/classifier-preprocess-read-probe.json`, `/tmp/parsing-xdm-webapp-probe.json`, `/tmp/parsing-xdm-webapp-probe2.json`, `/tmp/correlation-rules-probe.json`, `/tmp/correlation-rules-delete-probe.json`.

---

## Path helper quick reference

```python
from cortex_ps_toolkit.core.paths import (
    incidentfields_list_url,
    incidentfield_write_url,
    incidentfield_delete_url,
    incidenttype_list_url,
    incidenttype_write_url,
    incidenttype_delete_url,
    classifier_search_url,
    preprocess_rules_list_url,
    layouts_list_url,
    layout_get_url,
    layout_delete_url,
    content_bundle_import_url,
    content_bundle_export_url,
    vc_uncommitted_url,
)
from cortex_ps_toolkit.platforms import Platform

host = "https://tenant.example.test"
platform = Platform.XSOAR8

# List incident types (web-app)
incidenttype_list_url(host, platform)
# → https://tenant.example.test/xsoar/incidenttype

# Delete incident type
# POST incidenttype_delete_url(host, platform)  body={"id": "My Type Name"}

# Delete incident field (web-app on cloud)
incidentfield_delete_url(host, platform, "incident_myfield")
# → https://tenant.example.test/xsoar/incidentfield/incident_myfield
```
