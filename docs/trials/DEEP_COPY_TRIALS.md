# Deep copy cross-tenant trials

Trials copy **root playbook + reachable sub-playbooks + referenced automation scripts** with `--overwrite`, then deep-compare each component on source vs target using `content/representation.py` normalization.

## Lab tenants (trial scope)

| Slug | Platform |
| --- | --- |
| `xsoar-japac-dev` | xsoar8 |
| `personal-xsoar6` | xsoar6 |
| `psojapac-xsiam` | xsiam |
| `cortex-cs-xdr5` | xdr5 |
| `cortex-cs-agentix` | agentix |

**Excluded from trials** (importable via `credentials import-lab` but not lab tenants): `bay-xsiam-1`, `bay-xsiam-2`, `mfec-uat`.

CLI:

```bash
python3 -m cortex_ps_toolkit playbooks copy-components-trial \
  --from-profile <source> \
  --name <root-playbook-name> \
  --lab-targets \
  --overwrite \
  --output docs/trials/<report>.json
```

Payload shaping reference: [PAYLOAD_CACHE_TO_UPLOAD.md](../PAYLOAD_CACHE_TO_UPLOAD.md).

Raw JSON reports: `series1-xsoar-japac-dev-main.json`, `series2-psojapac-xsiam-alt.json`.

---

## Series 1 — `Test_PB_Inv_Data_Main` from `xsoar-japac-dev` (xsoar8)

Targets: `personal-xsoar6`, `psojapac-xsiam`, `cortex-cs-xdr5`, `cortex-cs-agentix`.

| Target | Platform | Copy | Fidelity (strict) |
| --- | --- | --- | --- |
| personal-xsoar6 | xsoar6 | OK | Fail — metadata (`isOverridable`, task `scriptId` UUID) |
| psojapac-xsiam | xsiam | OK | Fail — platform envelope + script arg defaults |
| cortex-cs-xdr5 | xdr5 | OK | Fail — same as xsiam |
| cortex-cs-agentix | agentix | OK | Fail — same as xsiam |

All components present on target after copy. See `series1-xsoar-japac-dev-main.json` for full diffs.

---

## Series 2 — `Test_PB_Inv_Data_Main_Alt` from `psojapac-xsiam` (xsiam)

Targets: `xsoar-japac-dev`, `personal-xsoar6`, `cortex-cs-xdr5`, `cortex-cs-agentix`.

| Target | Platform | Copy | Fidelity (strict) |
| --- | --- | --- | --- |
| xsoar-japac-dev | xsoar8 | OK | Fail — XSOAR8 strips xsiam envelope fields on load |
| personal-xsoar6 | xsoar6 | OK | Fail — cross-platform envelope + binding shape |
| cortex-cs-xdr5 | xdr5 | OK | Fail — 1 component (`Unexpanded_Sub_Alt` `dirtyInputs`) |
| cortex-cs-agentix | agentix | OK | Fail — sub `dirtyInputs` + script `Print` metadata |

See `series2-psojapac-xsiam-alt.json` for full diffs.

---

## Post-refinement (per-sub-playbook cache refresh)

After each sub-playbook upload, the toolkit now **force-refreshes the target playbooks cache** and rebuilds `playbook_name_to_id` / `playbook_id_remap` before saving the next playbook in the tree. Script phase unchanged: scripts first → refresh scripts cache → bind script UUIDs.

---

## Gap taxonomy

### A. Upload / binding (real copy logic)

| Gap | Platforms | Status |
| --- | --- | --- |
| Sub-playbook `playbookId` remap | XSIAM/XDR/AgentiX | Addressed via `playbook_id_remap` |
| Script `scriptId` remap | XSIAM/XDR/AgentiX | Addressed via `script_id_remap` |
| Sub-playbook name-only binding | XSOAR 6/8 | Working |
| XSOAR6 overwrite via JSON `/automation` | xsoar6 | Working |

### B. Fidelity normalizer (comparison-only)

These fields appear on **target load** but not source cache export; should be ignored or canonicalized in `representation.py`:

| Field / path | Seen on |
| --- | --- |
| `adopted` | xsiam, xdr5, agentix playbooks |
| `contentitemexportablefields` / `isoverridable` | xsiam, xdr5, agentix playbooks |
| `isOverridable` (top-level) | xsoar6 playbooks → `None` after copy |
| `tasks.*.task.scriptId` UUID | xsoar6 (harmless; name-bound) |
| Script `args[].deprecated`, `args[].hidden` | xsiam/xdr/agentix |
| Script `important`, `isInternal` | xsoar6 |

### C. Payload schema transforms (cache → upload)

Documented in [PAYLOAD_CACHE_TO_UPLOAD.md](../PAYLOAD_CACHE_TO_UPLOAD.md).
