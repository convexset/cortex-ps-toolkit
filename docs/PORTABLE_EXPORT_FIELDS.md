# Portable export field policy (code + docs)

This document is the **authoritative reference** for how the toolkit shapes **playbook**, **script**, and **integration definition** YAML when you:

- export a **bundle ZIP**,
- **copy** content to another tenant on a YAML path (XSOAR 6, XSIAM ZIP, etc.), or
- build YAML for **manual XSOAR 6 import**.

**Goal:** Match **XSOAR 6 tenant / pack UI exports**, not raw tenant API JSON dumped to YAML. Raw API YAML often breaks legacy import (msgpack, `view` type, wrong ids).

**Policy is code-only.** It is **not** in `server.config.yaml`. To change rules, edit the Python modules below, update this doc, and run tests.

---

## Where to change code

| Concern | Module | Used by |
| --- | --- | --- |
| Exclude / include lists | `cortex_ps_toolkit/portable_export_fields.py` | `playbooks/portable_yaml.py`, `scripts/upload_prep.py`, `scripts/portable_yaml.py`, `integrations/portable_yaml.py` |
| Key remaps (API → YAML) | `cortex_ps_toolkit/portable_export_remaps.py` | `playbooks/yaml_export.py`, `scripts/upload_prep.py`, `integrations/portable_yaml.py` |
| Integration YAML export | `cortex_ps_toolkit/integrations/portable_yaml.py` | `integrations/yaml_export.py`, bundle ZIP, integration copy |
| Playbook prep (views, field mapping items) | `cortex_ps_toolkit/playbooks/upload_prep.py` | Copy + portable export |
| Bindings (script / sub-playbook ids) | `cortex_ps_toolkit/playbooks/yaml_bindings.py` | Copy (platform-specific) |
| Pack metadata block | `cortex_ps_toolkit/content/content_item_export.py` | Portable export |

**Introspection (read-only):**

```bash
python -m cortex_ps_toolkit portable-export show-policy
curl -s http://127.0.0.1:8770/api/portable-export-policy | jq .
```

**Server config** (`data/server.config.yaml`) covers logging, cache TTL threshold, and copy binding retries only.

---

## Processing pipeline (order matters)

### Playbooks

```
GET playbook JSON (cache)
  → prepare_playbook_for_portable_export / prepare_playbook_for_save
       · drop _private keys
       · view object → JSON string
       · fieldMapping[].fieldId → incidentfield  (item renames)
       · version / id rules for copy vs export
  → prepare_playbook_bindings_for_upload + finalize_subplaybook_fields_for_yaml
       · scriptName / playbookName (XSOAR 6); UUID bindings on XSIAM
  → _strip_portable_metadata
       · drop exclude_top_level / exclude_inner_task
  → merge contentitemexportablefields (pack block)
  → rename_playbook_keys_for_yaml
       · recursive key_renames + preserve_key_case
  → dumps_yaml
```

### Scripts

```
GET automation JSON (cache)
  → prepare_script_for_save
       · drop script exclude set
       · version -1; id rules for copy
  → script_to_yaml_export
       · script key_renames (arguments→args, …)
  → script_to_portable_yaml_document (bundle)
       · commonfields, core + optional include fields
  → dumps_yaml
```

---

## Playbooks

### 1. Keys removed (`DEFAULT_PLAYBOOK_EXCLUDE_TOP_LEVEL`)

Applied in `playbooks/portable_yaml._strip_portable_metadata` (case-insensitive match).

| Category | Keys |
| --- | --- |
| Search / ES | `cacheVersn`, `sequenceNumber`, `primaryTerm`, `modified`, `created`, `sizeInBytes`, `sortValues`, `highlight`, `syncHash`, `numericId`, `indexName` |
| Pack at wrong level | `packID`, `packName`, `itemVersion`, `fromServerVersion`, `toServerVersion`, `definitionId`, `propagationLabels` |
| VC / audit | `commitMessage`, `shouldCommit`, `vcShouldIgnore` |
| Denormalized | `taskIds`, `scriptids`, `brands`, `commands`, `missingScriptsIds` |
| Naming | `nameraw`, `prevName`, `isOverridable` |

Pack fields are **relocated** to `contentitemexportablefields.contentitemfields` before top-level pack keys are stripped.

### 2. Inner task keys removed (`DEFAULT_PLAYBOOK_EXCLUDE_INNER_TASK`)

Applied on each `tasks[*].task` dict:

- Same ES metadata keys as above (where present on inner task)
- **`scriptId` / `scriptid`** — portable YAML uses **`scriptName`** or **`script`** (brand command), not tenant script UUID

### 3. Keys kept (reference — top level)

Not a strict runtime whitelist; this is the **expected** portable / pack shape:

| Key | Notes |
| --- | --- |
| `name`, `id`, `version` | Portable export sets **`id` = `name`**; import uses **`version: -1`** |
| `starttaskid`, `tasks`, `view` | `view` must be a **JSON string**, not a mapping |
| `description`, `inputs`, `outputs` | Kept when present |
| `vcShouldKeepItemLegacyProdMachine` | When set on source |
| `contentitemexportablefields` | Pack metadata block |

Task nodes also retain canvas structure: `taskid`, conditions, `scriptarguments`, `nexttasks`, task `view` (string), flags such as `separatecontext`, `quietmode`, `ignoreworker`, and **`scriptName`** / **`script`**.

### 4. Key remaps (`DEFAULT_PLAYBOOK_KEY_RENAMES`)

Recursive rename in `rename_playbook_keys_for_yaml`: API camelCase → lowercase YAML keys accepted by `/playbook/save/yaml`.

Examples: `startTaskId`→`starttaskid`, `nextTasks`→`nexttasks`, `scriptArguments`→`scriptarguments`, `quietMode`→`quietmode`, `evidenceData`→`evidencedata`.

Full table: `portable_export_remaps.py` or `portable-export show-policy --section playbooks`.

### 5. Preserve key case (`DEFAULT_PLAYBOOK_PRESERVE_KEY_CASE`)

These keys are **not** lowercased when renaming the tree:

- `scriptName`
- `playbookName`
- `exitCondition`
- `inputSections`
- `fieldMapping` (container key; items inside still remap)

### 6. Field mapping item renames

Inside each task’s `fieldMapping[]` / `fieldmapping[]` entry:

| API | YAML |
| --- | --- |
| `fieldId` | `incidentfield` |

Constant: `DEFAULT_PLAYBOOK_TASK_FIELD_MAPPING_ITEM_RENAMES` in `portable_export_remaps.py`. Applied in `playbooks/upload_prep._rewrite_field_mapping_for_yaml`.

### 7. Other playbook transforms (not in exclude/remap tables)

| Transform | Location |
| --- | --- |
| Empty `evidencedata: {}` removed | `portable_yaml._strip_empty_evidence` |
| Sub-playbook UUID dropped on XSOAR 6 | `yaml_bindings` / `finalize_subplaybook_fields_for_yaml` |
| Task default flags filled | `portable_yaml._ensure_playbook_task_defaults` |

---

## Scripts

### 1. Keys removed (`DEFAULT_SCRIPT_EXCLUDE`)

Applied in `scripts/upload_prep._drop_server_keys` during `prepare_script_for_save`.

| Category | Keys |
| --- | --- |
| ES / audit | `cacheVersn`, `modified`, `created`, `sequenceNumber`, `primaryTerm`, `user`, `shouldCommit`, `shouldPublish`, `commitMessage`, … |
| Pack at top level | `packID`, `packName`, `itemVersion`, `fromServerVersion`, `toServerVersion`, `definitionId`, `propagationLabels` |
| UI / search | `searchableName`, `visualScript`, `nativeImage`, `contextKeys`, `rawTags` |
| Flags | `permitted`, `isInternal`, `locked` |
| Engine duplicate | `MainEngineInfo` |

Top-level **`id`** is omitted on **new copy**; portable export uses **`commonfields.id` = script name**.

### 2. Keys emitted (portable YAML)

**Always (core):** `commonfields`, `name`, `script`, `type`, `subtype`, `tags`, `enabled`, `runas`, `runonce`, `scripttarget`, `pswd`, `engineinfo`, `mainengineinfo`, `vcShouldKeepItemLegacyProdMachine`, and `contentitemexportablefields` when pack metadata exists.

**When present on source (optional):** `args`, `comment`, `dockerimage`, `system` (pack scripts).

Defined as `DEFAULT_SCRIPT_INCLUDE_CORE` / `DEFAULT_SCRIPT_INCLUDE_OPTIONAL` in `portable_export_fields.py`; optional list drives `scripts/portable_yaml.py`.

### 3. Key remaps (`DEFAULT_SCRIPT_KEY_RENAMES`)

Applied in `script_to_yaml_export`:

| API (JSON) | YAML |
| --- | --- |
| `arguments` | `args` |
| `dockerImage` | `dockerimage` |
| `scriptTarget` | `scripttarget` |
| `runAs` | `runas` |
| `runOnce` | `runonce` |

**XSOAR 8 JSON copy** keeps camelCase on the JSON save path; remaps apply to YAML/bundle paths only.

---

## Integrations (custom definitions)

Integration **instances** are never exported or copied; only **ModuleConfiguration** definitions (YAML upload / bundle `integrations/*.yml`).

Reference samples:

| Role | Path |
| --- | --- |
| Old bundle export (anti-pattern) | `scratch/xsoar-samples/current_bundle_export__ProtectedHTTPCall.yml` |
| XSOAR UI export | `scratch/xsoar-samples/ProtectedHTTPCall.yml` |

### Pipeline

```
ModuleConfiguration JSON (cache configuration_bodies)
  → configuration_to_portable_yaml_document
       · prune config params, commands, arguments, outputs
       · script block: dockerimage / runonce / nativeimage; omit false fetch/feed flags
       · top-level: commonfields, vcShouldKeepItemLegacyProdMachine, signature, restrictioncenter
  → configuration_to_yaml_text (bundle export + integrations copy upload)
```

### Keys dropped

| Area | Examples |
| --- | --- |
| Top-level API metadata | `fromServerVersion` (no default `fromversion`), pack/ES fields in `DEFAULT_INTEGRATION_EXCLUDE_CONFIGURATION` |
| Config params | `displayPassword`, `hidden*`, `options`, API `info` (renamed) |
| Commands | `cartesian`, `definitionId`, `permitted`, `polling`, `execution`, … |
| Arguments | `secret`, `hidden`, `deprecated`, empty `type`, false `default` / `required` |
| Outputs | empty `contentPath` |
| Script block | `feed`, `isFetch*` when false ( **`runonce` kept** even when false) |

### Key remaps

| API (JSON) | YAML |
| --- | --- |
| `detailedDescription` | `detaileddescription` |
| `defaultValue` (config param) | `defaultvalue` |
| `info` (config param) | `additionalinfo` |
| `dockerImage` | `dockerimage` |
| `nativeImage` | `nativeimage` |
| `restrictionCenter` | `restrictioncenter` |

Full lists: `portable-export show-policy --section integrations` or `GET /api/portable-export-policy`.

---

## Maintenance checklist

When XSOAR UI export format changes:

1. Refresh samples under `scratch/xsoar-samples/tenant_export__*.yml` (see [`BUNDLE_PORTABLE_EXPORT.md`](BUNDLE_PORTABLE_EXPORT.md)).
2. Update constants in `portable_export_fields.py` / `portable_export_remaps.py`.
3. Update **this document** (tables above).
4. Run:

```bash
cd cortex-ps-toolkit
python3 -m pytest tests/test_portable_export_reference.py tests/test_playbooks_portable_yaml.py tests/test_integrations_portable_yaml.py -q
```

---

## Related docs

| Doc | Content |
| --- | --- |
| [`BUNDLE_PORTABLE_EXPORT.md`](BUNDLE_PORTABLE_EXPORT.md) | Bundle ZIP behaviour, sample paths, anti-patterns |
| [`PAYLOAD_CACHE_TO_UPLOAD.md`](PAYLOAD_CACHE_TO_UPLOAD.md) | Full copy pipeline, platform matrix |
| [`api/toolkit/WEB-API.md`](api/toolkit/WEB-API.md) | `GET /api/portable-export-policy` |
