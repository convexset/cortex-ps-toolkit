# Prior art

Existing tools and libraries to **reuse, port, or wrap** when implementing Cortex PS Toolkit. Prefer adaptation over reinvention.

---

## Playbook refactor and cache

| Resource | Path | Reuse for |
| --- | --- | --- |
| Playbook utils package | [`bay/playbook-utils/`](../../bay/playbook-utils/) | Extract, compare, cache, client, refactor descriptions |
| Agent guide | [`bay/playbook-utils/AGENTS.md`](../../bay/playbook-utils/AGENTS.md) | Extract pipeline, refactor descriptions, task updates |
| Credentials loader | `playbook_utils/credentials.py` | JSON format, platform detection — **extend cache_key with api_id** |
| Playbook cache | `playbook_utils/cache.py` | TTL, manifest, index, refresh — **change root path** |
| HTTP client | `playbook_utils/client.py` | XSOAR 6/8/XSIAM endpoints, save/yaml, delete |
| Refactor descriptions | `playbook_utils/refactor_descriptions.py` | Parent/sub description text, metrics log |
| Playbook tree walk | `playbook_utils/playbook_tree.py` | Sub-playbook resolution for analysis |
| Graph checks | `playbook_utils/graph.py` | Potential root (A), cluster (C) preflight |

**Gap to close:** playbook-utils `Credentials.cache_key` is `host/tenant_type` only. Toolkit requires `host/tenant_type/api_id`.

---

## XQL query monitor

| Resource | Path | Reuse for |
| --- | --- | --- |
| HTML tool | [`bay/utilities/xql-query-monitor.html`](../../bay/utilities/xql-query-monitor.html) | Full UX reference: presets, grid, charts, credential profiles |
| README | [`bay/utilities/README.md`](../../bay/utilities/README.md) | API flow, preset catalog, timestamp rules, visualisation matrix |
| Local server | `bay/utilities/serve-xql-monitor.py` | Same-origin proxy pattern for web phase |

**Port to Python:**

- Preset query text (five built-ins)
- `parseTimestamp` / column inference rules
- Visualisation schema matchers (`playbook_run_performance`, `playbook_task_errors`, …)
- Hourly bucket labelling (local timezone)

**Do not port:** browser `localStorage` credential storage → replace with server-side credential files.

---

## Playbook metrics (offline / snapshot)

| Resource | Path | Reuse for |
| --- | --- | --- |
| Task characterisation | [`ai/scripts/xsoar_playbook_metrics.py`](../../ai/scripts/xsoar_playbook_metrics.py) | Automation ratio, task kinds, recursive metrics |
| Workflow analysis | [`ai/scripts/xsoar_incident_workflow_analysis.py`](../../ai/scripts/xsoar_incident_workflow_analysis.py) | Playbook tabulation across incident types |
| Schema reference | [`ai/guidance-sources/xsoar-6-data-schema.md`](../../ai/guidance-sources/xsoar-6-data-schema.md) | Task characterisation semantics |
| Playbook YAML tool | [`ai/tools/playbook_yaml/`](../../ai/tools/playbook_yaml/) | Offline YAML analysis when no live tenant |

Live toolkit uses **cached tenant JSON** instead of design-time snapshot exports, but metrics logic is the same.

---

## Documentation and API reference

| Resource | Path | Use when |
| --- | --- | --- |
| XQL language | [`ai/guidance-cache/cortex-xql-documentation.md`](../../ai/guidance-cache/cortex-xql-documentation.md) | Query syntax, datasets |
| XSOAR 8 Core API | [`ai/guidance-cache/xsoar--xsoar-8-core-api.md`](../../ai/guidance-cache/xsoar--xsoar-8-core-api.md) | Playbooks, scripts, incidents |
| Integrations guide | [`ai/guidance-cache/xsoar--integrations-and-scripts.md`](../../ai/guidance-cache/xsoar--integrations-and-scripts.md) | Integration development patterns |
| Cortex doc search | `python3 -m tools.cortex_docs search "..."` from `ai/` | Find current API URLs |
| XSOAR test rig | [`ai/test-tooling/AGENTS.md`](../../ai/test-tooling/AGENTS.md) | Integration unit test patterns (content authoring) |

---

## Engagement examples

| Resource | Path | Use as |
| --- | --- | --- |
| BAY refactor prompts | [`bay/scratch/bay-prompts.md`](../../bay/scratch/bay-prompts.md) | Reference scenario text (not a required toolkit benchmark; use MFEC UAT presets) |
| Phishing playbook facts | [`bay/scratch/phishing-playbook-facts.md`](../../bay/scratch/phishing-playbook-facts.md) | Expected metrics, task counts, refactor scope |
| BAY phishing YAML assets | [`bay/phishing-playbook/`](../../bay/phishing-playbook/) | Offline playbook_yaml analysis |

---

## PDF / stakeholder reporting (optional later)

| Resource | Path | Use when |
| --- | --- | --- |
| SOC automation PDF | [`gic/pdf-report-generation/`](../../gic/pdf-report-generation/) | Stakeholder playbook automation reports |
| Workflow analysis CLI | `ai/scripts/analyze_incident_workflows.py` | Incident-type automation rankings |

---

## What not to merge blindly

| Item | Reason |
| --- | --- |
| playbook-utils cache directories | Wrong cache key (missing api_id) |
| XQL monitor localStorage keys | Browser-only; incompatible with server credential model |
| demisto-sdk Docker lint | Content **authoring** on packs — different scope from tenant PS toolkit |
| Hardcoded credential paths in bay scripts | Replace with profile manager |

---

## Suggested first port checklist (Phase 1)

1. Copy `credentials.py` → add `profile_id`, extend `cache_key` with `api_id`
2. Copy `cache.py` → parameterise cache root from new `cache_key`
3. Copy `client.py` → minimal changes
4. Wire CLI `credentials list` + `cache refresh --scope playbooks`
5. Add test proving two api_ids on same host produce separate cache dirs
