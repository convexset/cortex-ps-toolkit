# Outstanding work (cortex-ps-toolkit)

Last updated: 2026-09-20.

Refactor/copy benchmarks use **MFEC UAT** (`mfec-uat`) — not BAY tenants. BAY phishing prompts remain reference scenarios in [`bay/scratch/bay-prompts.md`](../../bay/scratch/bay-prompts.md) but are **not** a required benchmark gate.

## Playbook analysis UX

- [ ] Task list view: searchable flat table of all tasks across the expanded tree (id, playbook, type, label, reachable).
- [ ] Flow graph: highlight path from start to selected task; show predecessor/successor counts in overview.
- [ ] Persist analysis panel section/tab choice per session.

## Copy & fidelity

- [ ] Re-run cross-platform fidelity after normalizer changes on lab tenant matrix ([`docs/trials/DEEP_COPY_TRIALS.md`](trials/DEEP_COPY_TRIALS.md)).
- [ ] Surface fidelity probe results in analysis UI when copy completes.

## Refactor

- [ ] Server-side validation of refactor ops in `/api/playbooks/refactor/preview` (mirror UI rules).
- [ ] Show matched task titles in error-handling preview (requires tenant cache lookup).

## Ops

- [ ] Scheduled cleanup of `data/playbook-utils-cache/jobs/` (cron or maintenance panel hook).
- [ ] Document benchmark `--repeat` workflow in [`data/refactor-benchmarks/README.md`](../data/refactor-benchmarks/README.md).

## Tests

- [ ] Integration test: copy-components round-trip on one lab pair (read-only source).
