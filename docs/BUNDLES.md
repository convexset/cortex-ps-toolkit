# Bundles — extended workflow copy and portable export

The **Bundles** section (`#/bundles` in the dev server) collects heterogeneous Cortex content into a **basket**, optionally saves it as a **preset** per source tenant, **copies** it to another profile in dependency order, or **exports** a portable ZIP for manual import (especially XSOAR 6).

Related:

| Doc | Topic |
| --- | --- |
| [`api/toolkit/bundles.md`](api/toolkit/bundles.md) | REST request/response shapes |
| [`BUNDLE_PORTABLE_EXPORT.md`](BUNDLE_PORTABLE_EXPORT.md) | Playbook/script/integration YAML shaping |
| [`PORTABLE_EXPORT_FIELDS.md`](PORTABLE_EXPORT_FIELDS.md) | Include/exclude/remap policy (code-only) |
| [`CONTENT-CLI.md`](CONTENT-CLI.md) | Design-content orchestrator (same design phase as bundle copy) |
| [`UI_STANDARDISATION_AND_COPY_ROADMAP.md`](UI_STANDARDISATION_AND_COPY_ROADMAP.md) | Copy confirm + result UX phases |

---

## Concepts

| Term | Meaning |
| --- | --- |
| **Basket** | In-memory list of `{ asset, id, name, type }` items selected from the catalog (not persisted until you save a preset). |
| **Saved preset** | Named bundle stored in `data/collections/object_setup_bundles.json` under `profiles.{source_slug}.{bundle_id}`. |
| **Resolve** | `POST /api/bundles/resolve` checks each basket member exists on the source tenant cache/API. |
| **Shallow playbooks** | Default for bundle copy: upload selected playbooks only; sub-playbook/script bindings may remain unresolved until dependencies exist on target (see `binding_table` in plan/result). |
| **Design phase** | Object-setup assets copied via `execute_cross_tenant_workflow` after content phases. |

---

## Copy phases (execute order)

When you run **Copy bundle to target**, the toolkit runs phases **only for assets present in the basket**:

1. **Integrations** — custom integration definitions (YAML upload); pack/system definitions are blocked at plan time.
2. **Scripts**
3. **Playbooks** — shallow copy by default (`shallow_playbooks: true` in API body).
4. **Lists**
5. **Design** — incident-fields → layouts → incident-types → classifiers → preprocess; optional correlation rules if included in basket.

Each phase uses the same copy-mode knobs as List/Script/Playbook tools (`overwrite`, `stop_on_conflict`, `copy_mode`, `rename_suffix`, `rename_map`). Integrations ignore rename / copy-as-new.

Preview: `POST /api/bundles/copy/preview` returns an **operation plan** (`plan_version: 1`) with nested sub-plans and warnings (e.g. shallow binding table).

---

## Web UI

| Area | Behaviour |
| --- | --- |
| **Workflow basket** | List above catalog; remove per item; dirty state vs last save/load. |
| **Catalog tabs** | Integrations, lists, scripts, playbooks, incident types, custom fields, layouts, classifiers, preprocess, correlation rules (capability-gated). |
| **In basket column** | Shows **Yes** when the catalog row matches an item in the basket (same asset tab only). Rows also get class `in-bundle` (subtle background). |
| **Copy row** | Target profile + copy mode controls (overwrite, stop on conflict, copy-as-new suffix, **Diff after copy**). |
| **Result block** | Alerts, text summary (per phase), collapsible JSON, **View classified copy diffs** when post-copy diff ran. |
| **Export** | Portable ZIP; optional save preset first. |
| **Dependencies** | Scan playbooks in basket for missing scripts/sub-playbooks. |

Copy today uses **HTTP** `POST /api/bundles/copy` with staged progress toasts. WebSocket job `bundles.copy` is available for long runs (same payload as HTTP); UI may adopt it later.

---

## Post-copy diff (bundle)

When `"post_copy_diff": true` on copy (UI: **Diff after copy**):

| Phase | Fidelity probe |
| --- | --- |
| Scripts | Yes — per-row `post_copy_diff`, phase `copy_diff_report` |
| Playbooks (shallow) | Yes |
| Lists | Yes |
| Integrations | No |
| Design / object-setup | No |

The HTTP response sets top-level `"post_copy_diff": true` and, when any probed phase ran diff, **`post_copy_diff_summary`** (merged counts) and **`copy_diff_report`** (flattened rows with `phase: name` labels). Per-phase reports remain under `results.scripts`, `results.playbooks`, etc.

Probe id and normalization rules: `cortex_ps_toolkit/content/representation.py` (`POST_COPY_DIFF_PROBE_ID`).

---

## Result shapes and success counting

**Lists / scripts / playbooks / integrations** use string statuses: `copied`, `updated`, `skipped`, `failed`.

**Design assets** often record **`status` as HTTP status code** (e.g. `200`) on each result row. Summaries and success toasts use `copy_entry_succeeded()` (`design_content/copy_progress.py`), which treats 2xx HTTP as success. The bundle result UI uses the same rules.

Nested execute response:

```json
{
  "operation": "bundles.copy",
  "source_profile": "...",
  "target_profile": "...",
  "post_copy_diff": true,
  "post_copy_diff_summary": { "matched": 0, "mismatched": 0, "errors": 0, "ignored_only": 0, "probe": "..." },
  "copy_diff_report": { "probe": "...", "rows": [], "row_count": 0 },
  "results": {
    "integrations": { "results": [] },
    "scripts": { "results": [], "post_copy_diff_summary": {}, "copy_diff_report": {} },
    "playbooks": { "results": [], "binding_table": [], "copy_diff_report": {} },
    "lists": { "results": [] },
    "design": {
      "executed": true,
      "halted": false,
      "assets": {
        "incident-fields": { "results": [{ "status": 200, "action": "update" }] }
      }
    }
  }
}
```

Aborted plan: `{ "aborted": true, "reason": "...", "plan": { ... }, "results": {} }`.

---

## Portable ZIP export

`POST /api/bundles/export` returns `application/zip` with paths such as:

- `integrations/{name}.yml`
- `scripts/{name}.yml`
- `playbooks/{name}.yml`
- Design JSON sections per asset kind

Export **fails closed** if any basket member is missing on source. Preview: `POST /api/bundles/export/preview`.

---

## Storage

Saved presets share Object Setup bundle storage:

- File: `data/collections/object_setup_bundles.json`
- API aliases: `/api/bundles/*` and `/api/object-setup/bundles/*`

---

## Modules (Python)

| Module | Role |
| --- | --- |
| `cortex_ps_toolkit/bundles/copy.py` | Plan + execute multi-phase copy |
| `cortex_ps_toolkit/bundles/export.py` | ZIP build + export plan |
| `cortex_ps_toolkit/bundles/dependencies.py` | Playbook dependency scan |
| `cortex_ps_toolkit/design_content/bundle_presets.py` | Resolve basket items on source |
| `cortex_ps_toolkit/design_content/orchestrator.py` | Design phase ordering |

---

## Testing

```bash
cd cortex-ps-toolkit
python3 -m pytest tests/test_bundle_integrations.py tests/test_bundle_export.py \
  tests/test_copy_notifications.py tests/test_bundle_copy_diff.py -q
```

Portable YAML reference tests optionally use `~/Downloads/dev/scratch/xsoar-samples/tenant_export__*.yml`; they **skip** if samples are absent.

---

## Known gaps / roadmap

- Design-phase post-copy diff not wired through bundle orchestrator.
- Bundle copy UI still uses HTTP + loader (WS `bundles.copy` implemented for parity with lists/scripts).
- Full operation-plan confirm shell unified across all tools (see UI standardisation roadmap Phase 1).
