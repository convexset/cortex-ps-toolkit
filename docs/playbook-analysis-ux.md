# Playbook analysis UI — UX model

## What analysts want to learn

| Goal | Where in the UI | Notes |
| --- | --- | --- |
| **What it looks like** — shape, branches, conditions | **Flow** | Primary visual; task # jump; saved-view placement matches tenant canvas |
| **Navigate** — find a task, see predecessors/successors | **Flow** + task detail pane | Click node; structure tree links into flow tabs |
| **Big picture structure** — nesting, repeated subs | **Structure** + Overview stats | Tree with (Nx) invocation counts |
| **Expanded summary** — automation vs manual, types | **Tasks** tabs + **Inventory** | Reachable / unreachable = expanded graph; All tasks = per-file reference; bindings in summary columns |
| **Every task in tree** — id, paths, branches | **Task list** | One row per task; Task # links to Flow graph; conditional branches + min/max steps from start/terminal |
| **Full task collection** | **Detail** (per-playbook) + flow raw JSON/YAML | Flat searchable table is a follow-up ([`OUTSTANDING.md`](OUTSTANDING.md)) |
| **Act** — refactor or copy | **Refactor** / **Copy** | Separated from read-only analysis sections |

**Refactor task pickers:** leaf and cluster operations use dropdowns from `refactor_task_catalog` (task id, title, truncated description). **Check validity** calls `POST /api/playbooks/refactor/validate-extract` (playbook-utils graph rules server-side). Error-handling match preview remains client-side against the analysis tree.

## Section order (top → bottom)

1. **Overview** — reachability, completion path, copy scope (orientation)
2. **Flow** — default focus after overview (visual exploration)
3. **Structure** — compact tree for hierarchy
4. **Tasks** — aggregated type/label counts (tabbed)
5. **Inventory** — scripts, playbooks, integration commands
6. **Detail** — per-playbook breakdown (collapsible)
7. **Refactor** / **Copy** — mutating operations last

Sticky **section nav** jumps between blocks without scrolling past unrelated content.

## Help pattern

- **?** button on section headings and complex controls
- Short text in `title` (hover); longer HTML in expandable detail or outcome dialog
- Error-handling refactor uses a **structured form** instead of raw `MATCH|actions` text

## Beginner-facing clarifications

| Term | Risk | Mitigation |
| --- | --- | --- |
| Reachable vs unreachable | Confused with “deleted” | Overview + Tasks tab help |
| Deep copy vs integration commands | Expects commands to copy | Inventory help + preview plan |
| Refactor parent copy | Fear of overwriting source | Refactor section help + confirm dialog |
| Cluster START:END | Invalid ranges | Inline validation |
| Error handling spec | Opaque DSL | Structured match/retry/on-error UI + generated spec preview |
| Parallel extract-multi | “Experimental” unclear | Help on checkbox |

## Future UX (see [`OUTSTANDING.md`](OUTSTANDING.md))

- Searchable flat task table across expanded tree
- Path highlight from start to selected task
- Fidelity summary after copy in-panel
