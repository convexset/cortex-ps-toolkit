# Operation plan schema (`plan_version: 1`)

Preview endpoints for copy operations return a versioned plan envelope so the web UI can render a consistent confirm dialog.

## Top-level fields

| Field | Type | Description |
| --- | --- | --- |
| `plan_version` | `1` | Schema version |
| `operation` | string | e.g. `lists.copy`, `playbooks.copy_shallow`, `playbooks.copy_components` |
| `copy_mode` | `skip` \| `overwrite` \| `copy_as_new` | Effective mode |
| `mode_description` | string | Human-readable outcome description for selected options |
| `source_profile` / `target_profile` | string | Tenant slugs |
| `summary` | object | `total`, `create`, `update`, `skip`, `abort` |
| `steps` | array | Ordered phases shown in confirm UI |
| `items` | array | Per-asset rows (`action`, `name`, optional `proposed_name`, …) |
| `risks` | array | `{ code, severity, message }` — high severity requires ack in UI |
| `warnings` | array | Non-blocking `{ code, message }` |
| `would_abort` | bool | Execute would refuse without plan change |
| `binding_table` | array | Shallow playbook copy: unresolved task bindings |

Legacy fields (`counts`, `conflicts`, `overwrite`, nested `scripts` / `playbooks` on deep copy) remain during transition.

## Copy mode API

Request body (all copy preview/execute routes):

| Field | Description |
| --- | --- |
| `copy_mode` | Optional: `skip`, `overwrite`, `copy_as_new` |
| `overwrite` / `stop_on_conflict` | Legacy booleans; ignored when `copy_mode` set |
| `rename_suffix` | Applied to selected items in `copy_as_new` mode (default `_copy`) |
| `rename_map` | Optional `{ source_id: new_name }` overrides |

## Delete plans

Delete preview routes wrap the same envelope with `operation` ending in `.delete` and `summary` keys `delete`, `blocked`, `skip` (instead of create/update). `would_delete` indicates whether execute will attempt removals.

## Name check (copy-as-new helper)

`POST /api/copy/name-check` — body `{ target_profile, kind, proposals[] }` or `{ target_profile, kind, items[], copy_mode, rename_suffix, rename_map? }`. Returns `{ checks: [{ key, source_name, proposed_name, exists, target_id }], collision_count, all_available }`.

## Endpoints emitting `plan_version: 1`

- `POST /api/lists/delete/preview` (and scripts, playbooks, integrations, design-content, platform-admin delete previews)
- `POST /api/playbooks/refactor/preview`
- `POST /api/lists/copy/preview`
- `POST /api/scripts/copy/preview`
- `POST /api/playbooks/copy/preview`
- `POST /api/playbooks/copy-shallow/preview`
- `POST /api/playbooks/copy-components/preview`
- `POST /api/bundles/copy/preview`
- `POST /api/integrations/copy/preview`
- `POST /api/design-content/{asset}/copy/preview`
- `POST /api/platform-admin/correlation-rules/copy/preview`
- `POST /api/platform-admin/biocs/copy/preview`
- `POST /api/platform-admin/indicators/copy/preview`

Legacy-only fields (`entries`, `has_conflicts`) are still present on design/admin previews for CLI compatibility; `items` and `summary` are authoritative for the UI.

## Client normalization

When a preview is wrapped only at the HTTP layer or nested under `{ plan: … }` (aborted execute), the dev server uses `normalizeConfirmPlan()` and `confirmCopyPlan()` in `web/static/operation-ui.js` before rendering the confirm dialog.
