# Content CLI — Lists, Playbooks, Scripts, Integrations

Unified command reference for cached **lists**, **playbooks**, **scripts**, and **integration definitions**.

Run from package root:

```bash
cd /Users/weichen/Downloads/dev/cortex-ps-toolkit
python3 -m cortex_ps_toolkit credentials list
```

All three resources share the same subcommand shape (lists adds `save`).

---

## Shared subcommands

| Subcommand | Purpose |
| --- | --- |
| `refresh --profile SLUG` | Fetch from tenant → update `data/cache/.../{lists,playbooks,scripts}/index.json` |
| `list --profile SLUG` | Print cached inventory (stdout table) |
| `show --profile SLUG --id ID` or `--name NAME` | Print one cached row as JSON |
| `copy-preview --from-profile A --to-profile B --id ID …` | Dry-run copy plan (conflicts, skip/update counts) |
| `copy --from-profile A --to-profile B --id ID …` | Copy selected items to target tenant |
| `delete-preview --profile SLUG --id ID …` | Dry-run delete plan (system blocked, not found) |
| `delete --profile SLUG --id ID …` | Bulk delete on tenant |

### Copy flags

| Flag | Effect |
| --- | --- |
| `--overwrite` | Replace existing item on target when names match |
| `--stop-on-conflict` | Abort entire copy if any name exists on target |

`--overwrite` and `--stop-on-conflict` are mutually exclusive.

Repeat `--id` for multiple items:

```bash
python3 -m cortex_ps_toolkit scripts delete --profile bay-xsiam-1 --id id1 --id id2
```

---

## Lists

Additional subcommand: **`save`** (create/update one list on tenant).

```bash
# Refresh
python3 -m cortex_ps_toolkit lists refresh --profile xsoar-japac-dev

# Browse cache
python3 -m cortex_ps_toolkit lists list --profile personal-xsoar6
python3 -m cortex_ps_toolkit lists show --profile personal-xsoar6 --name InternalDomains

# Create / update
python3 -m cortex_ps_toolkit lists save --profile personal-xsoar6 \
  --name MyList --data "line1\nline2" --type plain_text

# Copy with preview
python3 -m cortex_ps_toolkit lists copy-preview \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --id InternalDomains --stop-on-conflict

python3 -m cortex_ps_toolkit lists copy \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --id InternalDomains --overwrite

# Bulk delete
python3 -m cortex_ps_toolkit lists delete-preview --profile personal-xsoar6 --id ListA --id ListB
python3 -m cortex_ps_toolkit lists delete --profile personal-xsoar6 --id ListA --id ListB
```

Platform support: `content.lists.manage` — see [`PLATFORMS.md`](PLATFORMS.md).

Agent guide: [`LISTS-AGENTS.md`](LISTS-AGENTS.md).

---

## Playbooks

```bash
python3 -m cortex_ps_toolkit playbooks refresh --profile psojapac-xsiam
python3 -m cortex_ps_toolkit playbooks list --profile psojapac-xsiam
python3 -m cortex_ps_toolkit playbooks show --profile psojapac-xsiam --id <uuid>

python3 -m cortex_ps_toolkit playbooks analyze --profile xsoar-japac-dev --id <uuid>

python3 -m cortex_ps_toolkit playbooks copy-preview \
  --from-profile xsoar-japac-dev --to-profile personal-xsoar6 \
  --id <uuid> --overwrite

# Optional fidelity check on execute (not preview): add --post-copy-diff to playbooks copy

python3 -m cortex_ps_toolkit playbooks copy-components-preview \
  --from-profile xsoar-japac-dev --to-profile personal-xsoar6 \
  --id <root-uuid>

python3 -m cortex_ps_toolkit playbooks copy-components \
  --from-profile xsoar-japac-dev --to-profile personal-xsoar6 \
  --id <root-uuid> --overwrite

# Optional: --post-copy-diff on copy-components (execute only)

python3 -m cortex_ps_toolkit playbooks delete-preview --profile personal-xsoar6 --id <uuid>
python3 -m cortex_ps_toolkit playbooks delete --profile personal-xsoar6 --id <uuid>

# Refactor (wraps playbook-utils extract-multi)
python3 -m cortex_ps_toolkit playbooks refactor-preview \
  --profile xsoar-japac-dev --id <uuid> \
  --task 366 --cluster 21:52 \
  --post-task-update 'contains:HttpV2:i|retry=30x30,stop-on-error'

python3 -m cortex_ps_toolkit playbooks refactor \
  --profile xsoar-japac-dev --id <uuid> \
  --task 366 --cluster 21:52 \
  --post-task-update 'contains:HttpV2:i|retry=30x30,stop-on-error'

# In-place task error-handling / context updates
python3 -m cortex_ps_toolkit playbooks update-tasks-preview \
  --profile xsoar-japac-dev --name-prefix '[REFACTOR-S]' \
  --update '8:retry=15x45'

python3 -m cortex_ps_toolkit playbooks update-tasks \
  --profile xsoar-japac-dev --playbook Test_PB_Main \
  --update '8:retry=15x45' --context-update '4:global'
```

Search endpoint: `POST /xsoar/public/v1/playbook/search` (compat on XSIAM/XDR/AgentiX). Lab verification: [`PLATFORMS.md`](PLATFORMS.md) § Verified compat endpoints.

Refactor platforms: XSOAR 6, XSOAR 8, XSIAM only (`playbooks.refactor.*` operations).

---

## Scripts

```bash
python3 -m cortex_ps_toolkit scripts refresh --profile cortex-cs-xdr5
python3 -m cortex_ps_toolkit scripts list --profile cortex-cs-xdr5
python3 -m cortex_ps_toolkit scripts show --profile cortex-cs-xdr5 --name PrintDebug

python3 -m cortex_ps_toolkit scripts copy \
  --from-profile xsoar-japac-dev --to-profile bay-xsiam-1 \
  --id <uuid> --overwrite

# Optional: --post-copy-diff on scripts copy (same semantics as playbooks copy)

python3 -m cortex_ps_toolkit scripts delete --profile bay-xsiam-1 --id <uuid>
```

Search endpoint: `POST /xsoar/public/v1/automation/search` (compat on XSIAM/XDR/AgentiX).

---

## Integrations

Custom integration **definitions** (not instances). Copy uploads demisto-style YAML;
delete posts the full ModuleConfiguration body from `integration/search`.

```bash
python3 -m cortex_ps_toolkit integrations refresh --profile xsoar-japac-dev
python3 -m cortex_ps_toolkit integrations list --profile personal-xsoar6
python3 -m cortex_ps_toolkit integrations show --profile personal-xsoar6 --name MyCustomIntegration

python3 -m cortex_ps_toolkit integrations copy-preview \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --id MyCustomIntegration --overwrite

python3 -m cortex_ps_toolkit integrations copy \
  --from-profile personal-xsoar6 --to-profile psojapac-xsiam \
  --id MyCustomIntegration --overwrite

python3 -m cortex_ps_toolkit integrations delete-preview \
  --profile personal-xsoar6 --id MyCustomIntegration

python3 -m cortex_ps_toolkit integrations delete \
  --profile personal-xsoar6 --id MyCustomIntegration
```

Platform support: `integrations.copy`, `integrations.delete` — see [`PLATFORMS.md`](PLATFORMS.md).

Web REST: [`api/toolkit/integrations.md`](api/toolkit/integrations.md)

---

## XQL (related)

```bash
python3 -m cortex_ps_toolkit xql run --profile psojapac-xsiam \
  --query "dataset = xdr_data | limit 5" --timeframe-hours 24
```

Platforms: `xsiam`, `xdr3`, `xdr5`, `agentix`.

Web REST: [`api/toolkit/xql.md`](api/toolkit/xql.md)

---

## Design content (Object Setup)

Incident fields, types, layouts, classifiers, pre-process rules — plus ordered cross-tenant workflow.

**Overwrite** on **incident fields** and **incident types** (direct `POST` on XSOAR 6/8): the toolkit strips server `version` from the payload, so an update can hit XSOAR’s optimistic-lock error. When the plan action is `update`, `cortex_ps_toolkit/content/overwrite_retry.py` deletes the target definition, waits 0.5s, then writes again (same path as bundle / orchestrator copy). The first failed write does **not** show a persistent error toast; the UI gets a **12s self-dismissing warning** that delete+retry is in progress. A persistent error appears only if the retry fails too.

```bash
python3 -m cortex_ps_toolkit design-content refresh --profile personal-xsoar6 --asset incident-fields
python3 -m cortex_ps_toolkit design-content list --profile personal-xsoar6 --asset layouts
python3 -m cortex_ps_toolkit design-content copy-preview \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --asset incident-fields --id myfield
python3 -m cortex_ps_toolkit design-content delete-preview --profile personal-xsoar6 --asset layouts --id layout-id
python3 -m cortex_ps_toolkit design-content orchestrate \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev \
  --selections-json '{"incident-fields":["field-a"],"layouts":["layout-a"]}' \
  --include-correlation-rules --correlation-rule-names RuleName
```

Web REST: [`api/toolkit/WEB-API.md`](api/toolkit/WEB-API.md) (Object Setup section).

**Saved copy bundles** (one identifier per **source profile**): `GET/POST /api/object-setup/bundles?profile=`, `GET/DELETE /api/object-setup/bundles/{id}?profile=`, `POST /api/object-setup/bundles/resolve`. Storage: `data/collections/object_setup_bundles.json` (v2: `profiles.{slug}.{bundle_id}`).

**Extended Bundles section** (web `#/bundles` + REST under `/api/bundles/*`): multi-phase copy, portable ZIP export, playbook dependency scan. No dedicated CLI subcommand yet — use REST from the dev server or call `copy_bundle_to_tenant` / `build_bundle_zip_bytes` from Python. See [`BUNDLES.md`](BUNDLES.md) and [`api/toolkit/bundles.md`](api/toolkit/bundles.md).

Example copy body (HTTP):

```json
{
  "source_profile": "xsoar-japac-dev",
  "target_profile": "personal-xsoar6",
  "items": [{ "asset": "scripts", "id": "MyScript", "name": "MyScript" }],
  "shallow_playbooks": true,
  "post_copy_diff": false,
  "overwrite": false
}
```

Delta since initial commit: [`CHANGELOG-post-initial-commit.md`](CHANGELOG-post-initial-commit.md).

---

## Platform admin (Indicators & correlation)

```bash
python3 -m cortex_ps_toolkit platform-admin refresh --profile psojapac-xsiam
python3 -m cortex_ps_toolkit platform-admin list --profile psojapac-xsiam --section biocs
python3 -m cortex_ps_toolkit platform-admin copy-indicators-preview \
  --from-profile personal-xsoar6 --to-profile xsoar-japac-dev --id 114
python3 -m cortex_ps_toolkit platform-admin copy-biocs \
  --from-profile psojapac-xsiam --to-profile cortex-cs-xdr5 --name "My BIOC"
python3 -m cortex_ps_toolkit platform-admin delete-correlation-rules-preview \
  --profile psojapac-xsiam --name "Rule Name"
python3 -m cortex_ps_toolkit platform-admin delete-indicators --profile personal-xsoar6 --id 114
python3 -m cortex_ps_toolkit platform-admin delete-biocs --profile psojapac-xsiam --name "My BIOC"
```

---

## Cache query

```bash
python3 -m cortex_ps_toolkit cache query --profile psojapac-xsiam --scope scripts \
  --name 'Print*' --origin custom
```

---

## Dev server & platforms

```bash
python3 -m cortex_ps_toolkit serve --host 127.0.0.1 --port 8770
python3 -m cortex_ps_toolkit paths
python3 -m cortex_ps_toolkit platforms list
python3 -m cortex_ps_toolkit platforms show playbooks.refactor.extract_multi
```

Full web API ↔ CLI map: [`api/toolkit/WEB-API.md`](api/toolkit/WEB-API.md)

---

## Python modules

| Resource | Cache | Copy | Delete | Service |
| --- | --- | --- | --- | --- |
| Lists | `lists/cache.py` | `lists/copy.py` | `lists/delete.py` | `lists/service.py` |
| Playbooks | `playbooks/cache.py` | `playbooks/copy.py` | `playbooks/delete.py` | `playbooks/service.py` |
| Scripts | `scripts/cache.py` | `scripts/copy.py` | `scripts/delete.py` | `scripts/service.py` |
| Integrations | `integrations/cache.py` | `integrations/copy.py` | `integrations/delete.py` | `integrations/service.py` |

CLI registration: `cortex_ps_toolkit/cli_content.py` → `register_content_cli()`;
integrations registered in `cortex_ps_toolkit/cli.py` (`INTEGRATIONS_CLI`).
