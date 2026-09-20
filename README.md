# Cortex PS Toolkit

Professional-services tooling for **Cortex XSOAR** and **Cortex XSIAM** tenants: credentials, content caches, XQL queries, playbook analysis/refactoring, and content management.

**Development approach:** build and refine **Python libraries first**, then expose them through a **local web server** started by a single script (`./scripts/dev-server.sh`) with **debug mode** and **Python auto-reload**. CLI remains available for automation.

---

## Status

**Early implementation.** Python package skeleton, platform matrix, credential import. See [`docs/`](docs/) for architecture and [`docs/PLATFORMS.md`](docs/PLATFORMS.md) for per-platform operation support.

| Document | Purpose |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, package layout, Python-first strategy |
| [`docs/CREDENTIALS_AND_CACHE.md`](docs/CREDENTIALS_AND_CACHE.md) | Credential files, cache keys, on-disk layout |
| [`docs/FEATURES.md`](docs/FEATURES.md) | Feature specifications (XQL, playbooks, content) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phased delivery plan |
| [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md) | Existing tools to reuse or port |
| [`docs/UI_AND_SERVER.md`](docs/UI_AND_SERVER.md) | Dev server, navigation, CDN UI, query history |
| [`docs/STORAGE.md`](docs/STORAGE.md) | JSON collections, cache layout, 15-min cleanup |
| [`docs/PLATFORMS.md`](docs/PLATFORMS.md) | Platform API docs, operation support matrix, lab tenants |
| [`docs/api/README.md`](docs/api/README.md) | Lists API per platform + toolkit REST (sample payloads) |
| [`AGENTS.md`](AGENTS.md) | Agent entry point |

### Quick start

```bash
cd /path-to/cortex-ps-toolkit
python3 -m pip install -r requirements-dev.txt
python3 -m cortex_ps_toolkit credentials import-lab
python3 -m cortex_ps_toolkit credentials list
python3 -m cortex_ps_toolkit platforms list
# Unit tests only (fast, no live tenant)
python3 -m pytest tests/ --ignore=tests/integration -q

# Integration tests (lab credentials required; ~20 min)
python3 -m pytest tests/integration -m integration -v

# Full suite
python3 -m pytest -q

# Line coverage (unit tests; pip install pytest-cov)
python3 -m pytest tests/ --ignore=tests/integration -q \
  --cov=cortex_ps_toolkit --cov-report=term-missing:skip-covered

# Web UI (port 8770 — not 8765, which is the XQL monitor)
./scripts/dev-server.sh
```

Content CLI (lists, playbooks, scripts, integrations): [`docs/CONTENT-CLI.md`](docs/CONTENT-CLI.md).  
List Tools agent guide: [`docs/LISTS-AGENTS.md`](docs/LISTS-AGENTS.md).

```bash
python3 -m cortex_ps_toolkit lists refresh --profile xsoar-japac-dev
python3 -m cortex_ps_toolkit playbooks list --profile psojapac-xsiam
python3 -m cortex_ps_toolkit scripts copy-preview --from-profile a --to-profile b --id <uuid>
python3 -m cortex_ps_toolkit integrations list --profile personal-xsoar6
python3 -m cortex_ps_toolkit integrations copy-preview --from-profile a --to-profile b --id MyIntegration
python3 -m cortex_ps_toolkit xql run --profile psojapac-xsiam --query "dataset = xdr_data | limit 5"
```

---

## Planned capabilities

| Area | Summary |
| --- | --- |
| **Credentials manager** | Profiles in server-side JSON collections (not browser `localStorage`) |
| **Content cache** | Per-credential JSON cache; playbook refresh also refreshes scripts |
| **XQL query tool** | Live queries, presets, visualisations, **query history by ID** (hover query, reload results) |
| **Playbook tools** | Navigate cache, refactor, copy playbooks / component subs+scripts to another tenant |
| **Script tools** | Navigate cache, copy scripts to another tenant |
| **Dev server** | One script; debug + auto-reload; background cleanup every 15 minutes |

---

## Intended layout (future)

```
cortex-ps-toolkit/
├── README.md
├── AGENTS.md
├── docs/
├── cortex_ps_toolkit/          # Python package (CLI + libraries)
│   ├── core/                   # credentials, cache, http client
│   ├── xql/                    # query runner, presets, viz specs
│   ├── playbooks/              # cache, metrics, refactor
│   └── content/                # scripts, integrations, rules, widgets
├── scripts/
│   └── dev-server.sh           # start local server (debug + reload)
├── data/                       # gitignored — JSON collections + cache
│   ├── collections/            # credentials.json, xql_queries.json, …
│   └── cache/
├── presets/                    # shipped XQL application presets (JSON)
└── web/                        # static shell + CDN-backed JS (Tabulator, Plotly)
```

---

## Security notes

- Credential files and cache directories **must not** be committed. See [`.gitignore`](.gitignore).
- The web app will run locally; credentials stay on the server filesystem, never sent to the browser except through a controlled proxy.
- Use dedicated API keys with least privilege (XQL-only keys for query features, content keys for playbook work).

