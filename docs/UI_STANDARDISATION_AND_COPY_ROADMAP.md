# UI standardisation and copy workflow roadmap

Planning document for Cortex PS Toolkit web UI: unified operation flows, navigability, and extended copy/bundle capabilities. Complements [`UI_AND_SERVER.md`](UI_AND_SERVER.md), [`FEATURES.md`](FEATURES.md), [`CONTENT-CLI.md`](CONTENT-CLI.md).

**Status:** Phases 0–3 implemented (2026-10-08); Phase 4 polish ongoing.

---

## Goals

1. **One procedural pattern** for mutating operations: preview plan → confirm (with risks) → execute → structured result (summary → detail → raw).
2. **One visual language** for grids, copy panels, dialogs, progress, and profile context.
3. **Clear information architecture** in the nav rail (including new **Bundles** section).
4. **Rich copy modes** (deep, shallow, rename-as-copy, solution bundles) without duplicating ad hoc UI per section.

---

## Clarifications needed (product / UX)

Answer these before Phase 2+ implementation; defaults below are suggested if you want to proceed without blocking.

| # | Topic | Question | Suggested default |
| --- | --- | --- | --- |
| C1 | **Settings vs Script Tools icon** | Both were ⚙. Script Tools → ⚙ per request. What icon for **Settings**? | Settings → **🔧** or **⚙️** with label disambiguation in `title=` only; prefer **🔧** for Settings rail. |
| C2 | **Shallow playbook copy scope** | “Shallow” = upload playbook document only, no script/sub fetches? Sub-playbook tasks bind by **name** on target only? | Yes: no script upload; sub-playbook calls resolved via target cache by `playbookName`; warn on missing subs. |
| C3 | **Multi-playbook shallow copy** | One confirmation for N playbooks, or one plan with N sections? | Single plan with per-playbook binding table + shared options. |
| C4 | **Rename suffix** | Global suffix for all ticked items, or per-row editable name? | Per-row optional suffix/default `{name}_copy`; bulk apply suffix to selection; server validates uniqueness. |
| C5 | **Deep copy rename** | Renaming root only vs every selected script/PB in tree? | User selects subset in plan UI (checkboxes on plan rows); default all conflicting names. |
| C6 | **Bundle membership** | Lists/scripts/playbooks in bundle: by **id** on source tenant only, or allow name-based entries? | Id on source profile; bundle stored per source profile (existing object-setup model). |
| C7 | **Bundle copy order** | Dependency order: scripts → sub-playbooks (waves) → playbooks → lists → design assets? | Reuse deep-copy wave logic where applicable; document fixed phase order in plan. |
| C8 | **Overwrite vs rename** | Mutual exclusive with stop-on-conflict, or rename as third mode? | Three modes: **skip**, **overwrite**, **copy as new name** (suffix); stop-on-conflict only for skip/overwrite. |
| C9 | **Correlation / integrations** | Include in unified copy plan/result in Phase 1? | Phase 3; lists/scripts/playbooks/design first. |

---

## Current state (brief audit)

| Area | Today | Gap |
| --- | --- | --- |
| **Confirm** | `showConfirmDialog` + hand-built text (`formatCopySummary`, `formatComponentsPlanSummary`, `formatPreviewEntries`) | No shared schema; risks/warnings inconsistent; design-content vs lists vs playbooks differ. |
| **Preview API** | `*/copy/preview` exists for lists, scripts, playbooks, components, design-content, integrations, correlation | Plans vary in shape (`items`, `entries`, `counts`, `warnings`); not all expose risks explicitly. |
| **Results** | Mix of `<pre>` JSON, `copy-result-ui` alerts, `copy-diff-panel`, toasts | Good diff panel; no unified **operation result** component for non-diff outcomes. |
| **Progress** | `operation-progress-ui`, WS jobs | Consistent for batch copy; refactor/deep copy partially aligned. |
| **Nav** | Icon rail; Object Setup includes bundle workflow inline | Bundle not first-class section; icons inconsistent with requested set. |
| **Playbook copy** | Grid bulk copy = full playbook docs; analysis panel = deep copy only | No explicit **shallow** multi-PB copy; no rename-as-copy. |

---

## Target architecture

### A. Server: operation plan schema

Introduce a **versioned** JSON shape returned by all `*/preview` and optionally echoed on execute:

```json
{
  "plan_version": 1,
  "operation": "playbooks.copy",
  "source_profile": "…",
  "target_profile": "…",
  "summary": { "total": 3, "create": 2, "update": 1, "skip": 0, "abort": false },
  "steps": [
    { "phase": 1, "label": "Refresh target scripts cache", "automated": true },
    { "phase": 2, "label": "Upload scripts (parallel)", "items": ["…"] }
  ],
  "items": [
    {
      "id": "…",
      "name": "MyScript",
      "action": "update",
      "target_id": "…",
      "risks": ["overwrite"],
      "warnings": ["System script — verify impact"]
    }
  ],
  "risks": [
    { "code": "OVERWRITE", "severity": "high", "message": "2 playbooks will replace existing names on target." }
  ],
  "warnings": [
    { "code": "MISSING_SUB", "message": "Sub-playbook 'Child' not on target; shallow copy may fail at runtime." }
  ],
  "would_abort": false,
  "abort_reason": null
}
```

**Implementation:** `cortex_ps_toolkit/content/operation_plan.py` (build helpers); migrate each `plan_*_copy` to emit this (keep legacy fields during transition).

### B. Server: operation result schema

Extend copy responses uniformly:

```json
{
  "telemetry": { "run_id": "…", "operation": "…" },
  "post_copy_diff": true,
  "post_copy_diff_summary": { … },
  "copy_diff_report": { … },
  "issues_summary": {
    "failed": 0,
    "warnings": 1,
    "flagged_diffs": 0,
    "ignored_diffs": 2
  },
  "results": [ … ]
}
```

`issues_summary` drives the UI top level; `copy_diff_report` drives nested diff UI (already implemented).

### C. Client: shared operation UI kit

New module **`web/static/operation-ui.js`** (names tentative):

| Component | Role |
| --- | --- |
| `renderOperationPlan(plan)` | HTML for confirm dialog: summary counts, steps, risks (red), warnings (amber), item table (collapsible). |
| `confirmOperation({ title, plan, proceedLabel })` | Wrapper over dialog; requires non-empty ack if `risks` contains `high`. |
| `presentOperationResult(container, result, options)` | Summary strip + expandable issues + link to diff panel + collapsed JSON. |
| `bindCopyOptions(formId)` | Shared overwrite / stop / post-diff / rename suffix controls. |

Deprecate per-file `formatCopySummary` strings over time; keep as fallback until all routes emit `plan_version`.

### D. Visual / navigability standardisation

| Element | Standard |
| --- | --- |
| **Page layout** | Title + meta cache line + grid + **Operations** panel (copy/delete) below grid; profile context under target select. |
| **Selection toolbar** | Same button order: count badge → select visible → all → none → primary actions. |
| **Copy row** | Target profile → mode checkboxes → diff after copy → primary button. |
| **Dialogs** | `app-dialog` + scrollable body; primary/destructive on right. |
| **Results** | Always: alerts (collapsible) → **View classified copy diffs** (if diff) → **Full JSON** `<details>`. |
| **Rail icons** | See [Navigation changes](#navigation-changes). |
| **Landing cards** | Mirror rail order; add Bundles card. |

CSS: consolidate under `web/static/styles.css` sections `--op-panel`, `--copy-row`, reuse analysis accordion patterns for plan review.

---

## Navigation changes

| Section | Icon (requested) | Route | Notes |
| --- | --- | --- | --- |
| List Tools | 📝 (unchanged) | `#/lists` | |
| Script Tools | **⚙️** | `#/scripts` | Was ⚙ (text variant); align emoji. |
| Playbook Tools | ▶️ | `#/playbooks` | |
| Integrations | 🔌 | `#/integrations` | |
| Object Setup | **📚** | `#/object-setup` | Was 🧰; **remove** bundle copy UI from this page. |
| **Bundles** | **💼** | `#/bundles` | **New**; workflow collector + save/load + cross-tenant copy. |
| XQL | 📊 | `#/xql` | |
| Indicators | 🎯 | `#/indicators` | |
| User Admin | 👥 | `#/system-admin` | |
| API Profiles | 🔑 | `#/credentials` | |
| Settings | **🔧** (proposed, see C1) | `#/settings` | Avoid duplicate ⚙ with Script Tools. |

Update [`UI_AND_SERVER.md`](UI_AND_SERVER.md) icon table when implemented.

---

## Feature workstreams

### 1. Deep copy — rename selected assets (create differently named copies)

**User story:** When target has name collisions, optionally copy **selected** scripts/playbooks under new names (suffix), rebind references in uploaded playbooks, without overwriting.

**Backend**

- Extend `plan_playbook_components_copy` with:
  - `rename_items: [{ source_id, kind, new_name }]` or global `name_suffix` + selected ids.
  - Target name availability check (cache-backed).
  - Plan rows: `action: copy_as_new`, `proposed_name`, `collision: false`.
- Execute path: create new entities; update `playbook_id_remap` / `script_id_remap` for bindings.
- Risks section: “N new objects; M task bindings will point to new ids.”

**Frontend (analysis panel + future unified confirm)**

- After preview plan fetch: table of conflicting assets with checkboxes + suffix field.
- Debounced `POST …/copy-components/preview` or lightweight `POST …/name-check` with proposed names.
- Requires stale-cache prompt for source+target playbooks+scripts (existing).

**Depends on:** operation plan schema, cache refresh API.

---

### 2. Shallow playbook copy (multi-select, binding-aware)

**User story:** Copy one or more **playbook documents** without pulling scripts; resolve sub-playbook and script references against **target** cache; optional wave copy of **missing** subs/scripts user approves in plan.

**Backend**

- New operation: `playbooks.copy_shallow` (or flag `depth=shallow` on existing copy).
- Preview:
  - For each selected playbook: list task refs (scriptName, playbookName).
  - Target resolution: exists / missing / would overwrite.
  - Optional phases: “Wave 1: copy missing scripts user selected”, “Wave 2: shallow PB uploads”.
- Diff from bulk copy today: bulk copy uploads full playbook YAML but does not run component tree; clarify product definition vs true shallow (no sub script upload).

**Frontend**

- Playbook grid: **Shallow copy selected** alongside **Copy selected** (deep document copy).
- Multi-select enabled (already); binding preview table in confirm plan.

**Open design:** True shallow may still need **one** wave of sub-playbook ID rebind after target refresh (reuse `copy_components` wave machinery subset).

---

### 3. Rename instead of overwrite (lists, scripts, shallow/deep playbooks)

**Unified copy modes** (replace overwrite checkbox trio over time):

| Mode | API flags (transition) | Behaviour |
| --- | --- | --- |
| Skip existing | `stop_on_conflict` or default skip | No upload |
| Overwrite | `overwrite: true` | Update by target id |
| Copy as new | `rename_suffix` / `rename_map` | New name; fail if proposed name exists |

**Backend:** extend `plan_*_copy` for lists, scripts, playbooks; validate names on target index.

**Frontend:** radio group or select; show rename suffix input when “Copy as new” selected; live name check.

---

### 4. Bundles section (solution bundles)

**User story:** Collect **design-time assets + lists + scripts + playbooks** from source tenant into a named bundle; copy bundle to another tenant in dependency order.

**Move from Object Setup**

- Extract bundle UI (`object-setup-ui.js` workflow/bundle/orchestrate) → **`bundles-ui.js`** + `#/bundles` panel in `index.html`.
- Object Setup retains: layouts, classifiers, preprocess, incident fields/types only.

**Extend bundle model**

- Today: `object-setup/bundles` stores design asset ids.
- Extend stored JSON: `{ design: [...], lists: [...], scripts: [...], playbooks: [...] }`.
- “Add to bundle” actions on List/Script/Playbook grids (cross-route via global bundle store or API session).

**Copy execution**

- Extend `design_content/orchestrate` or new `bundles/copy`:
  - Phases: scripts → playbooks (wave) → lists → design assets (existing bundle import).
- Single operation plan with risks aggregated.

**API:** `GET/POST /api/bundles`, `POST /api/bundles/copy/preview`, `POST /api/bundles/copy`.

---

## Phased delivery plan

### Phase 0 — Documentation and quick wins (1–2 days)

- [ ] Resolve clarifications C1–C9.
- [ ] Update rail icons (Script ⚙️, Object Setup 📚, Settings 🔧, add Bundles 💼 placeholder route “Coming soon” optional).
- [ ] Align landing page cards with rail.
- [x] Document copy/diff UX in [`docs/FEATURES.md`](FEATURES.md) (post-copy diff, classified panel, bundles result shell).

### Phase 1 — Unified confirm + result shell (1–2 weeks)

- [x] Define `operation_plan.py` + JSON schema doc in `docs/api/toolkit/operation-plan.md`.
- [x] Migrate **lists**, **scripts**, **playbooks** preview endpoints to emit `plan_version: 1`.
- [x] Implement `operation-ui.js`: plan confirm dialog with risks/warnings sections.
- [x] Wire lists, scripts, playbooks, shallow copy, deep copy, bundles, integrations, object-setup to `confirmCopyPlan` / `confirmOperation`.
- [x] Integrations, design-content, and platform-admin previews emit `plan_version: 1` via `wrap_legacy_preview_plan`.

**Exit criteria:** Every bulk copy in List/Script/Playbook Tools uses server plan in confirm; results show summary + expandable issues + diff panel + JSON. **Mostly met** — delete flows and refactor confirm remain bespoke.

### Phase 2 — Copy modes: rename / shallow (2–3 weeks)

- [x] Backend: `copy_mode`, `rename_suffix`, `rename_map` on lists, scripts, playbooks, design, bundle phases.
- [x] Backend: `POST /api/copy/name-check` (target cache collision probe for copy-as-new).
- [x] Frontend: per-item `rename_map` editor + live name-check on copy rows.
- [x] Delete previews emit `plan_version: 1`; UI uses `confirmDeletePlan` / `confirmOperation`.
- [x] Refactor preview wrapped as operation plan; analysis panel uses unified confirm.
- [x] Backend: shallow multi-playbook preview + execute (binding table in bundle + playbook shallow copy).
- [x] Frontend: copy mode controls + suffix via `appendCopyModeControls` (live name-check API still open).
- [x] Deep copy: `copy_as_new` upload names in `copy_components` (per-component rename map in analysis UI still open).

**Exit criteria:** Lab tenant demo: shallow 2 PBs with missing sub warning; rename script on conflict without overwrite. **Mostly met** in unit tests + lab manual QA item in [`BUNDLES.md`](BUNDLES.md).

### Phase 3 — Bundles section (2–3 weeks)

- [x] New `#/bundles` route; catalog + basket UI.
- [x] Extended bundle persistence (saved presets) + multi-asset catalog.
- [x] Bundle copy preview/execute with phased plan + integration phase.
- [x] Portable ZIP export + dependency scan.
- [x] Bundle copy result UI (alerts, summary, diff panel, JSON) — [`BUNDLES.md`](BUNDLES.md).
- [x] WS job `bundles.copy` (HTTP remains default in UI).
- [x] Wire Bundles copy button to WS progress (like List Tools).
- [x] Unified operation-plan confirm for bundle warnings (binding table + phase table in confirm dialog).

**Exit criteria:** Save bundle with layouts + 2 playbooks + scripts; copy to second tenant with plan + diff report. **Met** (HTTP + WS via `createOperationProgress`).

### Phase 4 — Polish and procedural hardening (ongoing)

- [x] Migrate design-content + platform-admin copy previews to operation plan schema (`wrap_legacy_preview_plan`).
- [x] Client `normalizeConfirmPlan` + `confirmCopyPlan` for nested/legacy preview bodies.
- [x] Post-copy diff on integrations/correlation (optional).
- [x] Accessibility pass (dialog focus restore on confirm; `details` keyboard still open).
- [ ] Optional: vend Tabulator/Plotly for offline (`web/static/vendor/`).
- [ ] E2E integration tests for preview → confirm → result JSON shapes.

---

## Testing strategy

| Layer | What |
| --- | --- |
| Unit | `operation_plan` builders; name collision; classified diff unchanged. |
| Integration | Preview endpoints return `plan_version`; rename/shallow flags on lab tenants. |
| UI manual | Script: copy with overwrite risk ack; diff panel 3-level expand; bundle multi-asset. |

---

## Files likely touched (reference)

| Concern | Paths |
| --- | --- |
| Plan schema | `cortex_ps_toolkit/content/operation_plan.py`, `tests/test_operation_plan.py` |
| Copy backends | `lists/copy.py`, `scripts/copy.py`, `playbooks/copy.py`, `playbooks/copy_components.py`, new shallow module |
| Bundles | `cortex_ps_toolkit/bundles/` or extend `object_setup/bundles.py` |
| API | `server/app.py`, `server/content_routes.py`, `server/design_content_api.py`, `docs/api/toolkit/*.md` |
| Web | `web/static/operation-ui.js`, `index.html`, `app.js`, `content-tools-ui.js`, `playbooks-analysis-ui.js`, `object-setup-ui.js`, new `bundles-ui.js`, `styles.css` |

---

## Relationship to recent work

The **classified copy diff** panel (`copy-diff-panel-ui.js`, probe `cptk.repr-copy-fidelity/v3`) is the **deepest result detail level**. Phase 1 should treat it as the standard third layer:

1. **Issues summary** (counts, failed uploads, flagged diffs).
2. **Classified diff report** (modal).
3. **Full JSON** (`<details>`).

No rework of diff logic required for Phase 1—only wiring through `presentOperationResult`.

---

## Next step

Confirm clarifications **C1–C9** (or accept defaults), then start **Phase 0 + Phase 1** with `operation_plan.py` and lists preview migration as the first PR-sized slice.
