# Cache representation → upload payload transforms

When copying playbooks and scripts, the toolkit loads **cache/search JSON** from the tenant API, then shapes it for the **save/insert** endpoint on the **target** platform. This document lists every intentional field change per tenant type.

Sources: `playbooks/upload_prep.py`, `playbooks/yaml_export.py`, `playbooks/yaml_bindings.py`, `playbooks/upload.py`, `scripts/upload_prep.py`, `scripts/upload.py`, `content/zip_payload.py`, `core/paths.py`.

---

## Shared (all platforms)

### Server-owned fields dropped before save

| Area | Keys removed |
| --- | --- |
| Scripts | `MainEngineInfo`, `cacheVersn`, `created`, `modified`, `definitionId`, `itemVersion`, pack metadata, commit flags, search index metadata |
| Playbooks | Private `_`-prefixed keys on playbook and task nodes |
| Playbooks (overwrite) | Requires target id; sets `version: -1` on playbook and inner task |

### Playbook structural prep (`prepare_playbook_for_save`)

| Cache field | Upload change |
| --- | --- |
| `view` (object) | JSON-stringified for YAML export |
| Task `view` | JSON-stringified |
| `fieldMapping[].fieldId` | Renamed to `incidentfield` |
| New copy | Top-level `id` removed; task `taskId` removed; inner task `id` removed |
| Overwrite | Top-level `id` = target playbook id; task ids retained |

### Playbook YAML key rename (`rename_playbook_keys_for_yaml`)

CamelCase API keys → lowercase YAML keys (e.g. `nextTasks` → `nexttasks`, `scriptId` → `scriptid`). Preserved as-is: `scriptName`, `playbookName`, `exitCondition`, `inputSections`, `fieldMapping`.

### Binding resolution (`prepare_playbook_bindings_for_upload`)

| Binding | XSOAR 6/8 | XSIAM / XDR / AgentiX |
| --- | --- | --- |
| Automation script tasks | Bind by **name** (`scriptName`); drop `scriptId` when not binding by id | Bind by **target UUID** (`scriptId` from remapped target cache) |
| Sub-playbook tasks | Drop `playbookId`; keep `playbookName` only | Keep **both** `playbookId` and `playbookName` (target UUIDs) |
| Cross-tenant copy | `script_id_remap` + `playbook_id_remap` applied before finalize | Same |

---

## Scripts by platform

| Step | xsoar8 | xsoar6 | xsiam / xdr5 / agentix |
| --- | --- | --- | --- |
| Save endpoint | `POST /xsoar/public/v1/automation` JSON | New: YAML import; Overwrite: JSON `/automation` | `POST /public_api/v1/scripts/insert` ZIP |
| Key casing | camelCase JSON (`dockerImage`, `arguments`) | YAML lowercase (`dockerimage`, `args`) | YAML lowercase + `commonfields` |
| Top-level `id` | Present on overwrite; omitted on create | Same | **Moved** to `commonfields.id`; top-level `id` removed |
| `version` | Set to `-1` on save prep | Same | Omitted from YAML body; `commonfields.version: -1` |
| `arguments` | Kept as `arguments` in JSON | Renamed to `args` in YAML | Renamed to `args` in YAML |
| `dockerImage` | camelCase in JSON | `dockerimage` in YAML | `dockerimage` in YAML |
| `runAs` / `runOnce` / `scriptTarget` | camelCase in JSON | lowercase in YAML | `runas`, `runonce`, `scripttarget` |
| Extra XSIAM fields | — | — | `pswd`, `engineinfo`, `mainengineinfo`, `signature` defaults added |

---

## Playbooks by platform

| Step | xsoar8 | xsoar6 | xsiam / xdr5 / agentix |
| --- | --- | --- | --- |
| Save endpoint | `POST /xsoar/public/v1/playbook/save/yaml` multipart | Legacy path (prefix stripped) multipart YAML | `POST /public_api/v1/playbooks/insert` ZIP |
| Payload shape | YAML text after key rename + binding finalize | Same | ZIP: `{name}.yml` + optional `metadata.json` |
| Sub-playbook refs | Name only | Name only | Id + name |
| Script task refs | Name only | Name only | Target `scriptId` UUID |

---

## Fidelity comparison ignores (`representation.py`)

Cross-tenant comparison normalizes before diffing:

| Category | Ignored / normalized |
| --- | --- |
| Identity | `id`, `name`, `version`, timestamps, cache/sync metadata |
| Playbooks | `view`, `description`, `comment`, denormalized `brands`/`commands`, task id lists |
| Sub-playbook refs | Compare by **name** only (UUIDs stripped) |
| Field mappings | `fieldId` → `incidentfield` |
| Scripts | `timeout`, `pswd`, `searchableName` |
| Key aliases | `dockerImage`/`dockerimage`, `arguments`/`args`, camelCase/lowercase |

Remaining diffs after copy indicate **real fidelity gaps** (payload shaping bugs or platform semantic differences).

---

## Known cross-platform gap patterns

| Symptom | Likely cause | Mitigation |
| --- | --- | --- |
| `dirtyInputs` differs on XDR/AgentiX | Platform adds/normalizes on insert | Add to `PLAYBOOK_IGNORE_KEYS` if cosmetic |
| Script `outputs` shape differs | XSIAM YAML omits or reshapes outputs | Extend `script_to_xsiam_yaml_export` |
| Sub-playbook not bound | Target cache stale or remap miss | Force refresh + `playbook_id_remap` after script copy |
| Script task unresolved | Target script missing or name mismatch | Copy scripts first; verify `script_id_remap` |
| `fieldMapping` mismatch | Source uses `fieldId`; target expects custom field name | Incident field must exist on target tenant |
