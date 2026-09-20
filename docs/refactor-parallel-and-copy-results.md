# Refactor parallelism & XSIAM copy — results (2026-09-20)

Summary of flow-graph UX polish, refactor parallelism work, per-job cache isolation, MFEC UAT phishing workflow benchmarks, and XSIAM deep-copy binding verification.

---

## 1. Flow graph — saved view polish

**Changes** (`web/static/playbooks-analysis-ui.js`, `web/static/styles.css`):

| Setting | Before (2×) | After (1.5×) |
| --- | ---: | ---: |
| Node width | 400 px | 300 px |
| Node height | 152 px | 114 px |
| Label font | 24 px | 18 px |
| Edge labels (saved view) | 24 px | 18 px |

**Text overflow fix:**

- Labels render inside `foreignObject` with flex-wrapped HTML instead of raw SVG `<text>`.
- Word-wrap helper (`flowSavedWrapText`) respects inner width; condition diamonds use a tighter effective width (~58%).
- Each node group has a `clipPath` so text cannot paint outside the shape bounds.
- CSS: `.flow-saved-node-text` / `.flow-saved-node-line` with `overflow: hidden` and `overflow-wrap: anywhere`.

**Use Saved View Placement** remains the default; unreachable nodes still render in a separate subgraph when not hidden.

---

## 2. Refactor parallelism

Three layers of parallelism:

| Layer | Mechanism | When |
| --- | --- | --- |
| **Within extract-multi** | `refactor_mode=parallel` → playbook-utils `extract_multi_parallel` | Leaf/cluster uploads inside one playbook refactor |
| **Workflow scope** | `execute_refactor_workflow(..., refactor_mode=parallel)` → `GraphExecutor` runs independent steps concurrently | Splunk + SIM phishing steps together |
| **Per-job cache** | `job_cache_key` → `data/playbook-utils-cache/jobs/<workflow>/<step>/` | Required when workflow steps run in parallel |

### API additions

```python
execute_refactor(..., job_cache_key="mfec-uat-full-workflow/mfec-uat-splunk-phishing")

build_extract_multi_args(..., job_cache_key=...)  # or explicit cache_dir=
playbook_utils_runtime(..., job_cache_key=...)
```

Workflow parallel automatically sets `job_cache_key = f"{workflow_id}/{step_id}"` for each step.

### Why per-job cache dirs matter

The first workflow-parallel attempt (`20260918T103826Z-parallel-workflow.json`) failed with shared cache corruption:

```
Expecting value: line 1 column 1 (char 0)
No such file or directory: .../playbook-utils-cache/.../Get_Original_Email_-_Microsoft_Graph_Mail.json
```

Splunk and SIM refactors were writing the same tenant cache tree concurrently. Isolated job directories prevent cross-step races.

---

## 3. MFEC UAT phishing workflow benchmarks

**Configuration:** `presets/refactor/mfec-uat-full-workflow.json`  
**Tenant:** `mfec-uat` (XSIAM)  
**Steps:** clear `[REFACTOR-*]` → Splunk phishing extract-multi → SIM phishing extract-multi

### Sequential vs parallel extract-multi (2026-09-18)

| Step | Sequential | Parallel extract-multi | Δ |
| --- | ---: | ---: | ---: |
| Clear | 22,207 ms | 16,504 ms | −25.7% |
| Splunk Phishing | 182,054 ms | 150,237 ms | −17.5% |
| SIM Phishing | 185,629 ms | 149,881 ms | −19.3% |
| **Total** | **389,893 ms** | **316,624 ms** | **−18.8%** |

Reports: `20260918T071453Z-toolkit-workflow-streaming.json`, `20260918T111452Z-parallel-extract-multi-v3.json`, comparison `20260918T111504Z-comparison.json`.

Splunk structural metrics (81 nodes moved, 7 subs): see `data/refactor-debug/.../12-refactor-metrics.txt`.

### Workflow-level parallel (v2)

Re-run after cache isolation:

```bash
python3 scripts/benchmark_mfec_refactor.py \
  --label parallel-workflow-v2 \
  --via-workflow --parallel --stream-progress \
  --output data/refactor-benchmarks/20260920T-parallel-workflow-v2.json
```

| Run | Total | Clear | Splunk | SIM | OK |
| --- | ---: | ---: | ---: | ---: | --- |
| Sequential stepwise | 389,893 ms | 22,207 ms | 182,054 ms | 185,629 ms | true |
| Parallel extract-multi (stepwise) | 316,624 ms | 16,504 ms | 150,237 ms | 149,881 ms | true |
| Workflow parallel v1 (shared cache) | 143,498 ms | 22,071 ms | — (failed) | — (failed) | **false** |
| **Workflow parallel v2 (isolated caches)** | **199,358 ms** | 23,045 ms | 175,319 ms* | 176,310 ms* | **true** |

\*Splunk and SIM ran concurrently; per-step elapsed times overlap. Wall-clock refactor phase ≈ max(175,319, 176,310) ≈ 176 s.

### Workflow v2 vs earlier modes

| Comparison | Total Δ | Δ % |
| --- | ---: | ---: |
| v2 vs sequential | −190,535 ms | **−48.9%** |
| v2 vs parallel extract-multi (stepwise) | −117,266 ms | **−37.0%** |

Report: `20260920T-parallel-workflow-v2.json`. Comparison: `20260920T-workflow-v2-comparison.json`.

Job cache keys confirmed in run output:

- `mfec-uat-full-workflow/mfec-uat-splunk-phishing`
- `mfec-uat-full-workflow/mfec-uat-sim-phishing`

Directories: `data/playbook-utils-cache/jobs/mfec-uat-full-workflow/{splunk,sim}-phishing/`.

---

## 4. XSIAM deep-copy re-test — binding & remap

**Command** (2026-09-20):

```bash
python3 -m cortex_ps_toolkit playbooks copy-components-trial \
  --from-profile personal-xsoar6 \
  --name Test_PB_Inv_Data_Main \
  --to-profile psojapac-xsiam \
  --overwrite \
  --output data/refactor-benchmarks/20260920T-xsiam-deep-copy-retest.json
```

**Report:** `data/refactor-benchmarks/20260920T-xsiam-deep-copy-retest.json`

### Copy outcome

| Check | Result |
| --- | --- |
| Copy completed | Yes — both playbooks + script updated |
| `binding_unresolved` (sub + root) | `[]` on all playbooks |
| `binding_issues` | `[]` |
| `playbook_id_remap` | Sub + root IDs mapped to target UUIDs |
| `script_id_remap` | `TEST_Show_Env` script remapped |

```json
"playbook_id_remap": {
  "7de7eb6f-b04b-47b0-8540-083ad3be6e8e": "7ea3b630-c06f-4906-8eb2-6839f26d261e",
  "c327dc1b-b70d-4507-8a49-d0195ccd8102": "ada66f83-724b-4c13-8408-c570b9d10b7c"
}
```

Binding enrichment from the source cache (`enrich_bindings_from_source_cache`) plus per-sub-playbook target cache refresh populates names before remap; no unresolved bindings on upload.

### Fidelity (strict compare)

`all_equal: false` — expected cross-platform envelope differences only (`adopted`, `contentitemexportablefields`, script arg metadata). No missing components on target. See [DEEP_COPY_TRIALS.md](trials/DEEP_COPY_TRIALS.md) gap taxonomy § B.

---

## 5. Analysis UI updates (2026-09-20)

**Refactor panel** (`web/static/playbooks-analysis-ui.js`):

- Single-playbook refactor only in the UI (load saved config, preview, run). Multi-step workflow presets remain CLI/benchmark-only (`scripts/benchmark_mfec_refactor.py --via-workflow`).
- **Structured progress** — timeline with phase labels; collapsible verbose log; post-run summary (elapsed ms, compare equal counts, parent copy name).

**Copy components** (analysis panel):

- **Preview copy plan** — shows plan counts plus UUID-only binding hints from flow-graph metadata.
- **Post-copy summary** — playbook/script ID remaps and unresolved binding list (alongside raw JSON).

**Flow graph**:

- **Structure tree** — sub-playbook names link to the matching flow graph tab.
- **Task detail** — “Add leaf extract” pre-fills refactor ops; “Open sub-playbook flow” switches tabs.
- **Saved view** — LR/TD layout buttons hidden when saved view placement is active; **node size** slider (1.0–2.0×) rescales saved-view nodes.

---

## 6. Tests

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python3 -m pytest \
  tests/test_refactor_job_cache.py \
  tests/test_refactor_workflow_parallel.py \
  tests/test_playbooks_binding_enrichment.py \
  tests/test_playbooks_playbook_remap.py \
  tests/test_playbooks_flow_graph.py -q
```

---

## Related files

| Topic | Path |
| --- | --- |
| Flow graph renderer | `web/static/playbooks-analysis-ui.js` |
| Per-job cache | `cortex_ps_toolkit/playbooks/refactor_bridge.py` |
| Workflow parallel | `cortex_ps_toolkit/playbooks/refactor_workflow.py` |
| Binding enrichment | `cortex_ps_toolkit/playbooks/binding_enrichment.py` |
| Benchmark CLI | `scripts/benchmark_mfec_refactor.py` |
| Benchmark index | `data/refactor-benchmarks/README.md` |
