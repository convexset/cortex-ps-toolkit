# Bundle copy — manual lab QA checklist

Run after copy-mode or bundle pipeline changes. Requires lab credentials (`python -m cortex_ps_toolkit credentials import-lab`).

## Automated preview smoke (no writes)

```bash
cd cortex-ps-toolkit
pytest tests/integration/test_bundle_copy_modes_lab.py -m integration -v
```

## Manual web UI (dev server)

```bash
./scripts/dev-server.sh
# http://127.0.0.1:8770/#/bundles
```

| Step | Copy mode | Diff after copy | Expected |
| --- | --- | --- | --- |
| 1 | Skip | off | Plan shows skip for existing names; execute skips collisions |
| 2 | Stop on conflict | off | Plan aborts when any selected name exists on target |
| 3 | Overwrite | on | Risks ack; updates in place; diff panel if enabled |
| 4 | Copy as new + suffix | on | Per-item map optional; name-check line green; new names on target |
| 5 | Mixed basket | on | Integrations + script + shallow playbook + list + one design asset; phased result + merged diff summary |

## CLI parity

```bash
python3 -m cortex_ps_toolkit bundles copy-preview \
  --from-profile xsoar-japac-dev --to-profile personal-xsoar6 \
  --items-file ./basket.json --copy-mode copy_as_new --rename-suffix _labqa
```

## Deep copy rebind (playbook analysis)

1. Deep-copy a playbook with a renamed sub-playbook (`copy_as_new` + suffix).
2. Confirm parent upload completes without unresolved sub-playbook binding for the **source** sub name.
