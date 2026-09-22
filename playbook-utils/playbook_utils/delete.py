"""Select and order playbooks for tenant delete."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence

from .client import PlaybookApiError
from .keys import JsonDict


DEFAULT_REFACTOR_NAME_PREFIX = "[REFACTOR"


def name_starts_with(name: str, prefix: str) -> bool:
    """Case-sensitive prefix match."""
    return str(name or "").startswith(prefix)


def order_playbooks_for_delete(rows: Sequence[Mapping[str, Any]]) -> list[JsonDict]:
    """Parents that call extracted subs first, then the subs themselves.

    ``[REFACTOR-M] …`` parent copies reference extracted sub-playbooks.
    Deleting the callee first can leave a dangling call or be refused.
    """

    def sort_key(row: Mapping[str, Any]) -> tuple:
        name = str(row.get("name") or "")
        is_sub = name.startswith((
            "[REFACTOR-S] ",
            "[REFACTOR-S-LEAF]",
            "[REFACTOR-S-INT]",
            "[REFACTOR-SUBPLAYBOOK]",
        ))
        return (1 if is_sub else 0, name.lower(), str(row.get("id") or ""))

    return [dict(row) for row in sorted(rows, key=sort_key)]


def delete_playbook_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    delete_fn: Callable[..., JsonDict],
    log: Optional[Callable[[str], None]] = None,
) -> list[JsonDict]:
    """Delete each row (already ordered). ``delete_fn`` is ``client.delete_playbook``."""
    outcomes: list[JsonDict] = []
    for row in rows:
        pid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        entry: JsonDict = {"id": pid, "name": name, "ok": False}
        if log:
            log(f"Deleting {name!r} ({pid})")
        try:
            if pid:
                response = delete_fn(playbook_id=pid, name=name or None)
            elif name:
                response = delete_fn(name=name)
            else:
                raise PlaybookApiError("row has neither id nor name")
            entry["ok"] = True
            entry["response"] = response
        except Exception as exc:
            entry["error"] = str(exc)
            if log:
                log(f"Failed {name!r} ({pid}): {exc}")
        outcomes.append(entry)
    return outcomes


def format_delete_text(outcomes: Sequence[Mapping[str, Any]], *, prefix: Optional[str] = None) -> str:
    lines = []
    if prefix:
        lines.append(f"Name prefix: {prefix!r} (case-sensitive)")
    ok = sum(1 for row in outcomes if row.get("ok"))
    failed = [row for row in outcomes if not row.get("ok")]
    lines.append(f"Deleted: {ok}/{len(outcomes)}")
    for row in outcomes:
        status = "ok" if row.get("ok") else "FAIL"
        lines.append(f"  [{status}] {row.get('id')}  {row.get('name')}")
        if row.get("error"):
            lines.append(f"         {row.get('error')}")
    if failed:
        lines.append(f"Failures: {len(failed)}")
    return "\n".join(lines)
