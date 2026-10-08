# Toolkit REST — Bundles

Extended workflow: basket, saved presets, multi-phase cross-tenant copy, portable ZIP export, playbook dependency scan.

Storage for saved presets: `data/collections/object_setup_bundles.json` (shared with Object Setup bundle APIs).

**CLI:** `python3 -m cortex_ps_toolkit bundles resolve|copy-preview|copy|export-preview|export` — see [`../../BUNDLES.md`](../../BUNDLES.md).

---

## GET /api/bundles?profile={slug}

List saved bundle presets for the **source** profile.

**Response `200`:** `{ "profile", "bundles": [ { "id", "name", "item_count", "updated_at" } ] }`

Aliases: `GET /api/object-setup/bundles?profile=`

---

## POST /api/bundles

Save a new preset.

**Request:**

```json
{
  "name": "phishing-workflow",
  "source_profile": "xsoar-japac-dev",
  "items": [
    { "asset": "playbooks", "id": "uuid-or-name", "name": "My Playbook" },
    { "asset": "incident-types", "id": "Phishing", "name": "Phishing" }
  ]
}
```

**Response `200`:** `{ "id", "name", "source_profile", "items", ... }`

---

## GET /api/bundles/{id}?profile={slug}

Load one preset.

---

## DELETE /api/bundles/{id}?profile={slug}

Delete preset on source profile.

---

## POST /api/bundles/resolve

Verify basket members on source (cache-backed).

**Request:** `{ "profile": "xsoar-japac-dev", "items": [ ... ] }`

**Response:** `{ "items": [ resolved rows ], "missing": [ ... ], "missing_count" }`

---

## POST /api/bundles/copy/preview

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "personal-xsoar6",
  "items": [ { "asset": "scripts", "id": "MyScript", "name": "MyScript" } ],
  "shallow_playbooks": true,
  "overwrite": false,
  "stop_on_conflict": false,
  "copy_mode": null,
  "rename_suffix": "",
  "rename_map": {}
}
```

Copy-mode fields match [`lists.md`](lists.md) / [`scripts.md`](scripts.md). Preview does **not** accept `post_copy_diff`.

**Response `200`:** Operation plan (`plan_version: 1`, `operation: "bundles.copy"`, `sub_plans`, `would_abort`, `warnings`, nested phase plans).

---

## POST /api/bundles/copy

Same body as preview, plus optional:

| Field | Default | Description |
| --- | --- | --- |
| `post_copy_diff` | `false` | After successful writes, run repr-copy-fidelity probe on **integrations**, **scripts**, **playbooks** (shallow), **lists**, and **design** assets in the basket (correlation rules when copied via design orchestrator). |
| `shallow_playbooks` | `true` | Shallow playbook upload; deep component copy is not used in bundle execute. |

**Response `200` (success):**

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "personal-xsoar6",
  "operation": "bundles.copy",
  "post_copy_diff": true,
  "post_copy_diff_summary": {
    "matched": 2,
    "mismatched": 0,
    "errors": 0,
    "ignored_only": 1,
    "probe": "cptk.repr-copy-fidelity/v4",
    "compare_mode": "normalized_json"
  },
  "copy_diff_report": {
    "probe": "cptk.repr-copy-fidelity/v4",
    "row_count": 3,
    "flagged_delta_total": 0,
    "ignored_delta_total": 4,
    "rows": [
      {
        "name": "scripts: MyScript",
        "status": "updated",
        "kind": "script",
        "outcome": "match_ignored_delta",
        "post_copy_diff": { }
      }
    ]
  },
  "results": {
    "integrations": { "source_profile", "target_profile", "results": [] },
    "scripts": { "results": [], "post_copy_diff_summary": {}, "copy_diff_report": {} },
    "playbooks": { "results": [], "binding_table": [], "copy_diff_report": {} },
    "lists": { "results": [] },
    "design": {
      "executed": true,
      "halted": false,
      "halt_reason": null,
      "assets": {
        "incident-fields": { "executed": true, "results": [ { "status": 200, "action": "update" } ] }
      }
    }
  }
}
```

**Aborted plan:** `{ "aborted": true, "reason": "...", "plan": { ... }, "results": {} }`

**Notifications:** Summary toast uses flattened rows and `copy_entry_succeeded()` (includes HTTP 2xx design rows). Per-item success toasts during progress when phases emit `item_copied` events.

**WebSocket:** Client may send `{ "action": "bundles.copy", "payload": { ...same body... } }` — see [`WEB-API.md`](WEB-API.md) WebSocket table.

---

## POST /api/bundles/export/preview

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "items": [ { "asset": "playbooks", "id": "...", "name": "..." } ],
  "bundle_name": "optional-label-for-zip"
}
```

Or `"bundle_id"` instead of inline `items` (loads saved preset).

**Response:** Plan with section counts and missing members (no tenant writes).

---

## POST /api/bundles/export

Same body as export preview.

**Response:** `application/zip` with `Content-Disposition: attachment; filename="..."`.

Portable YAML rules: [`../../BUNDLE_PORTABLE_EXPORT.md`](../../BUNDLE_PORTABLE_EXPORT.md).

---

## POST /api/bundles/playbook-dependencies

**Request:**

```json
{
  "source_profile": "xsoar-japac-dev",
  "playbook_ids": [ "uuid1", "uuid2" ],
  "basket_items": [ ]
}
```

**Response:** Rows for scripts and sub-playbooks referenced by the playbooks, with `selectable`, `in_bundle`, `reason` flags for the UI dependency list.

---

## GET /api/portable-export-policy

Introspection for portable export include/exclude/remap rules (playbooks, scripts, integrations). See [`../../PORTABLE_EXPORT_FIELDS.md`](../../PORTABLE_EXPORT_FIELDS.md).
