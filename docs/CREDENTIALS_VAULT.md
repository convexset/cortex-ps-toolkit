# Local integration credential vault

Separate from **tenant API profiles** (`data/collections/credentials.json`), the vault stores reusable integration secrets (username, password, certificates) for one-way push to tenants.

## Storage

```
data/vault/integration-credentials.vault.json
```

Encrypted at rest. File mode `0600` when the OS allows it.

## Cryptography

- Random **VMK** (256-bit) encrypts all vault entries
- Each **passphrase wrap slot** stores `Encrypt(KDF(passphrase), VMK)` with Argon2id + AES-256-GCM
- Passphrase **aliases** (e.g. `personal`, `team-break-glass`) identify slots for add/revoke — passphrases are never stored

## Operations

| Action | Requires |
| --- | --- |
| Initialize | New passphrase + alias |
| Unlock | Any valid passphrase |
| Add passphrase slot | Current valid passphrase + new passphrase + alias |
| Revoke passphrase slot | Any remaining valid passphrase + alias to revoke (not the passphrase being revoked) |
| Add/edit entries | Unlocked vault |

Minimum **one wrap slot** must remain.

## Tenant API (read-only cache)

`POST /xsoar/public/v1/settings/credentials` returns metadata only (`hasPassword`, `user`, `name`, …). Secrets cannot be read back from tenants.

## Future: push to tenant

`PUT /settings/credentials` will create/update tenant credentials from vault entries (planned; not enabled in UI yet).

## Web UI

**Integrations → Local vault** tab: unlock/lock, manage wrap slots, add entries.

## CLI

Vault management is exposed via HTTP API (`/api/vault/*`) used by the web UI. CLI wrappers can be added alongside `credentials` commands.
