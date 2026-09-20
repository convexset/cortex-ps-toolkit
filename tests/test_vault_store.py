from __future__ import annotations

from pathlib import Path

import pytest

from cortex_ps_toolkit.vault import store


@pytest.fixture()
def isolated_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault_file = tmp_path / "integration-credentials.vault.json"
    monkeypatch.setattr(store, "vault_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "vault_path", lambda: vault_file)
    return vault_file


def test_vault_init_unlock_add_wrap_and_entry(isolated_vault: Path) -> None:
    store.init_vault("alpha-pass", alias="personal")
    assert isolated_vault.is_file()
    store.lock_vault()

    store.unlock_vault("alpha-pass")
    entry = store.add_entry(name="Splunk Admin", user="admin", password="secret")
    assert entry["name"] == "Splunk Admin"
    assert entry["has_password"] is True
    store.lock_vault()

    store.unlock_vault("alpha-pass")
    rows = store.list_entries(masked=True)
    assert len(rows) == 1
    assert rows[0]["name"] == "Splunk Admin"


def test_vault_second_passphrase_wrap(isolated_vault: Path) -> None:
    store.init_vault("alpha-pass", alias="personal")
    store.add_passphrase_wrap(
        current_passphrase="alpha-pass",
        new_passphrase="beta-pass",
        alias="team",
    )
    store.lock_vault()

    store.unlock_vault("beta-pass")
    assert len(store.list_entries(masked=True)) == 0

    store.add_entry(name="Service Account", user="svc", password="pw")
    store.lock_vault()

    store.unlock_vault("alpha-pass")
    assert len(store.list_entries(masked=True)) == 1


def test_vault_revoke_passphrase_wrap(isolated_vault: Path) -> None:
    store.init_vault("alpha-pass", alias="personal")
    store.add_passphrase_wrap(
        current_passphrase="alpha-pass",
        new_passphrase="beta-pass",
        alias="team",
    )
    store.revoke_passphrase_wrap(passphrase="alpha-pass", alias="team")
    store.lock_vault()

    with pytest.raises(store.VaultPassphraseError):
        store.unlock_vault("beta-pass")

    store.unlock_vault("alpha-pass")
    wraps = store.list_wraps()
    assert len(wraps) == 1
    assert wraps[0]["alias"] == "personal"
