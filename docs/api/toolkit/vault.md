# Toolkit REST — Credentials vault

Local encrypted vault at `data/vault/` (VMK + alias passphrase wrap slots). **No tenant API** — independent of Cortex credential endpoints.

See [`../../CREDENTIALS_VAULT.md`](../../CREDENTIALS_VAULT.md) for crypto model and operator workflow.

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/vault/status` | GET | Initialized / unlocked state |
| `/api/vault/init` | POST | Create vault + first wrap slot |
| `/api/vault/unlock` | POST | Unlock with passphrase |
| `/api/vault/lock` | POST | Lock session |
| `/api/vault/wraps` | GET | List wrap slot aliases |
| `/api/vault/wraps` | POST | Add wrap slot (new passphrase) |
| `/api/vault/wraps/revoke` | POST | Revoke slot by alias (any other valid passphrase) |
| `/api/vault/entries` | GET | List entry metadata |
| `/api/vault/entries` | POST | Create entry |

**CLI:**

```bash
python3 -m cortex_ps_toolkit vault status
python3 -m cortex_ps_toolkit vault init --passphrase '…' --alias primary
python3 -m cortex_ps_toolkit vault unlock --passphrase '…'
python3 -m cortex_ps_toolkit vault entries
python3 -m cortex_ps_toolkit vault wraps
python3 -m cortex_ps_toolkit vault lock
```

**Operation:** `vault.manage` (all platforms — local feature).

Master table: [`WEB-API.md`](WEB-API.md)
