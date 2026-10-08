# Bundle portable export — playbook, script & integration YAML

Bundle ZIP exports under `playbooks/` and `scripts/` are shaped for **manual import on XSOAR 6** (Settings → Objects → Import, or legacy `/playbook/save/yaml` / automation YAML save). They must **not** be raw tenant API JSON dumped to YAML.

Reference comparisons (lab samples):

| Role | Path |
| --- | --- |
| Old bundle export (anti-pattern) | `scratch/xsoar-samples/current_bundle_export__*.yml` |
| XSOAR 6 UI export — custom | `scratch/xsoar-samples/tenant_export__Test_PB_Inv_Data_Main.yml`, `tenant_export__TEST_Show_Env.yml` |
| XSOAR 6 UI export — **pack content** | `tenant_export__AutoFocusPolling.yml`, `tenant_export__RunPollingCommand.yml`, `tenant_export__AddKeyToList.yml` |

Implementation: `cortex_ps_toolkit/playbooks/portable_yaml.py`, `cortex_ps_toolkit/scripts/portable_yaml.py`, `cortex_ps_toolkit/integrations/portable_yaml.py`.

**Integration definitions** (custom only, no instances): `integrations/*.yml` via `integrations/yaml_export.py` → portable shaping; bundle copy phase runs before scripts. Pack/system definitions are resolved in the catalog but blocked at copy/export (same rules as Integrations → Copy).

Compare `scratch/xsoar-samples/current_bundle_export__ProtectedHTTPCall.yml` (raw API-shaped YAML) with `ProtectedHTTPCall.yml` (tenant UI export).

Related: [`PAYLOAD_CACHE_TO_UPLOAD.md`](PAYLOAD_CACHE_TO_UPLOAD.md) (tenant **copy** upload path).

---

## Playbooks

### What the old bundle export included (unnecessary / harmful)

These come from **GET playbook JSON** (often XSOAR 8) and should **not** appear in portable YAML:

| Category | Examples | Why drop |
| --- | --- | --- |
| Search / ES metadata | `cacheversn`, `sequenceNumber`, `primaryTerm`, `modified`, `sizeinbytes`, `sortValues`, `highlight`, … | Server-owned; can break msgpack decode on XSOAR 6 |
| Pack metadata at **top level** | Raw API `packID`, `packName`, … | Relocate to **`contentitemexportablefields.contentitemfields`** (pack UI shape) |
| VC commit noise | `commitMessage`, `shouldCommit`, `vcShouldIgnore`, `propagationLabels` | Drop |
| Denormalized indexes | `taskids`, `scriptids`, `brands`, `commands`, `missingScriptsIds` | Rebuilt by server from tasks |
| Naming noise | `nameraw`, `prevName`, `isOverridable` | Export / audit fields |
| Wrong binding shape | `scriptid` on automation tasks | XSOAR 6 YAML expects `scriptName` (or `script` for `Brand\|\|\|command`) |
| Sub-playbook UUIDs | `playbookid` on tasks (cross-tenant) | XSOAR 6 binds sub-playbooks by **`playbookName`** only |
| Wrong `view` type | Nested YAML mapping for `view` | Must be a **JSON string** (literal block) for save/yaml msgpack |
| Stale versions | `version: 20`, inner task `version: 2` | Portable **new** import uses **`version: -1`** |
| Wrong top-level `id` | Tenant UUID from XSOAR 8 API | Set to **`name`** (pack-style string id) for portable YAML |
| Empty clutter | `evidencedata: {}` on tasks | Omit when empty |

### Necessary fields (custom + pack tenant exports)

Portable export **keeps** these when present on source (see pack examples):

| Field | Playbook | Script |
| --- | --- | --- |
| `id` | String id (= `name` for pack content) | via `commonfields.id` (= `name`) |
| `version` | Playbook `-1` on import; pack UI may show `1` | `commonfields.version` (typically `-1` on import) |
| `contentitemexportablefields` | Pack playbooks | Pack scripts |
| `vcShouldKeepItemLegacyProdMachine` | Yes | Yes |
| `description` | Yes (from `comment` if needed) | — |
| `inputs` / `outputs` | Yes | — |
| `starttaskid`, `tasks`, playbook `view` | Yes | — |
| Task `taskid`, inner task `id` | Yes (portable export preserves canvas ids) | — |
| Task `view`, `scriptarguments`, conditions | Yes | — |
| Task flags | `separatecontext`, `note`, `timertriggers`, `ignoreworker`, `skipunavailable`, `quietmode`, `isoversize`, `isautoswitchedtoquietmode` | — |
| `scriptName` / `script` | Not `scriptid` | — |
| `commonfields` | — | Always (cross-tenant: id = script name) |
| `system` | — | When source is pack/system script |
| `args`, `comment`, `dockerimage`, `enabled`, `runas`, … | — | Yes |

Helper: `content/content_item_export.py` builds the pack block from API `packID` / `packName` / … before those keys are stripped for upload.

### Code paths

| Path | Playbook shaping |
| --- | --- |
| **Bundle ZIP export** | `build_portable_playbook_yaml()` |
| **Playbook copy to tenant** | `save_playbook_document()` → `prepare_playbook_for_save` + bindings + `rename_playbook_keys_for_yaml` (same family) |
| ~~`get_playbook` + `dumps_yaml`~~ | **Do not use** for export |

---

## Scripts

### What the old bundle export included (unnecessary)

Raw `automation/load` JSON, including:

| Category | Examples | Why drop |
| --- | --- | --- |
| Identity on cross-tenant export | top-level `id` | New import: omit (XSOAR 6 YAML create) |
| ES / audit | `cacheVersn`, `sequenceNumber`, `primaryTerm`, `modified`, `sizeInBytes`, `user`, `shouldCommit`, … | Same as `SCRIPT_DROP_KEYS` in `scripts/upload_prep.py` |
| Pack / flags | `packID`, `system`, `permitted`, `isInternal`, `locked`, … | Not needed for save |
| UI / search | `searchableName`, `visualScript`, `nativeImage`, `contextKeys`, `rawTags`, … | Server-side |
| Wrong key names | `arguments`, `dockerImage`, `runAs`, `scriptTarget` | YAML uses `args`, `dockerimage`, `runas`, `scripttarget` |
| Engine duplicates | `MainEngineInfo`, top-level `engine` / `engineGroup` | Use empty `engineinfo` / `mainengineinfo` in YAML export |

### What tenant UI export keeps (portable export aligns here)

| Field | Notes |
| --- | --- |
| `name`, `script`, `type`, `subtype`, `tags`, `enabled` | Core |
| `runas`, `runonce`, `scripttarget`, `pswd` | Lowercase YAML keys |
| `engineinfo`, `mainengineinfo` | Often `{}` |
| `vcShouldKeepItemLegacyProdMachine` | Optional flag |
| `args` | When script has arguments (renamed from API `arguments`) |
| `dockerimage` | When set |
| `commonfields` | Pack exports use **`id: <script name>`**. Portable export always emits this block (import-friendly; not the source tenant UUID). |
| `contentitemexportablefields` | Emitted when source has pack metadata (from API or pack install). |
| `system` | Preserved when `true` on source (pack scripts). |

### Code paths

| Path | Script shaping |
| --- | --- |
| **Bundle ZIP export** | `build_portable_script_yaml()` |
| **Script copy (XSOAR 6 YAML create)** | `save_script_document()` → `script_to_portable_yaml_document(prepared)` |
| **Script copy (XSOAR 8)** | JSON `save_script_json` (unchanged) |
| **Script copy (XSIAM / XDR / AgentiX)** | `script_to_xsiam_yaml_export()` + ZIP insert |
| **`get_script_yaml()`** | Delegates to `build_portable_script_yaml()` |

---

## Integrations

### What the old bundle export included (unnecessary)

| Category | Examples | Why drop / reshape |
| --- | --- | --- |
| Default version noise | `fromversion: 6.0.0` from `fromServerVersion` | UI export omits unless pack-managed |
| Wrong description key | `detailedDescription` | UI uses `detaileddescription` |
| Config param API fields | `defaultValue`, `info`, `displayPassword`, `options: null` | UI uses `defaultvalue`, `additionalinfo`; drop hidden/display password placeholders |
| Command metadata | `cartesian`, `definitionId`, `permitted`, `polling`, … | Not in UI YAML |
| Argument noise | `secret`, `hidden`, empty `type`, false `default` | UI keeps only meaningful args |
| Script flags | `feed: false`, `isFetch: false`, … | Omit when false; keep `runonce` |

### Code paths

| Path | Integration shaping |
| --- | --- |
| **Bundle ZIP export** | `configuration_to_yaml_text()` |
| **Integration copy (YAML upload)** | `copy_integrations_to_tenant()` → same helper |

Field policy: [`PORTABLE_EXPORT_FIELDS.md`](PORTABLE_EXPORT_FIELDS.md) § Integrations.

---

## Maintenance

When XSOAR UI export format changes, refresh samples under `scratch/xsoar-samples/tenant_export__*.yml` and compare top-level keys:

```bash
cd cortex-ps-toolkit
python3 -m pytest tests/test_portable_export_reference.py -q
```

Include/exclude/remap rules are **code-only** — see [`PORTABLE_EXPORT_FIELDS.md`](PORTABLE_EXPORT_FIELDS.md). Introspection: **`GET /api/portable-export-policy`** or `python -m cortex_ps_toolkit portable-export show-policy`.

When rules change, update `portable_export_fields.py` / `portable_export_remaps.py`, this doc, `PORTABLE_EXPORT_FIELDS.md`, and `tests/test_portable_export_reference.py`.
