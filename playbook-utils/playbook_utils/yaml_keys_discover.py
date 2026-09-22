"""Discover YAML key spellings from an exported playbook YAML.

`/playbook/save/yaml` ignores many camelCase keys. Tenant YAML exports show the
spellings that actually persist. This module:

1. Inventories every YAML key as written.
2. For API JSON tasks, serializes distinctive scalar values, finds them in the
   YAML text, and reads the adjacent key name (walking up if the value sits
   under a nested `simple:` / list item).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .keys import JsonDict, playbook_tasks


_KEY_LINE = re.compile(r"^([ \t]*(?:-[ \t]+)?)([A-Za-z_][A-Za-z0-9_]*)[ \t]*:")
_YAML_KEY = re.compile(r"^[ \t]*(?:-[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*:", re.M)

# Values that match too many YAML sites to be useful on their own.
_WEAK_VALUES = frozenset(
    {
        "",
        "true",
        "false",
        "null",
        "0",
        "1",
        "-1",
        "title",
        "start",
        "stop",
        "regular",
        "condition",
        "playbook",
        "collection",
        "simple",
        "complex",
    }
)


@dataclass
class ValueHit:
    task_id: str
    json_path: str
    json_key: str
    yaml_key: str
    value: str
    line: int

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "json_path": self.json_path,
            "json_key": self.json_key,
            "yaml_key": self.yaml_key,
            "value": self.value,
            "line": self.line,
        }


@dataclass
class DiscoverResult:
    yaml_keys_lower: List[str]
    yaml_keys_mixed: List[str]
    renames: Dict[str, str]
    preserve: List[str]
    hits: List[ValueHit] = field(default_factory=list)
    unmatched: List[JsonDict] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "yaml_keys_lower": list(self.yaml_keys_lower),
            "yaml_keys_mixed": list(self.yaml_keys_mixed),
            "renames": dict(self.renames),
            "preserve": list(self.preserve),
            "hits": [h.to_dict() for h in self.hits],
            "unmatched": list(self.unmatched),
        }

    def human_summary(self) -> str:
        lines = [
            f"YAML keys (lowercase): {len(self.yaml_keys_lower)}",
            f"YAML keys (mixed/camelCase, preserve on upload): {len(self.yaml_keys_mixed)}",
        ]
        if self.yaml_keys_mixed:
            lines.append("preserve:")
            for key in self.yaml_keys_mixed:
                lines.append(f"  {key}")
        lines.append(f"API camelCase → YAML spelling: {len(self.renames)}")
        for src, dst in self.renames.items():
            lines.append(f"  {src} → {dst}")
        if self.hits:
            lines.append(f"value-adjacent hits: {len(self.hits)}")
            for hit in self.hits:
                if hit.json_key != hit.yaml_key:
                    lines.append(
                        f"  task {hit.task_id} {hit.json_path}: {hit.json_key!r} "
                        f"→ {hit.yaml_key!r} (value {hit.value!r}, line {hit.line})"
                    )
        if self.unmatched:
            lines.append(f"unmatched distinctive values: {len(self.unmatched)}")
        return "\n".join(lines)


def inventory_yaml_keys(yaml_text: str) -> Dict[str, Set[str]]:
    """Map lowercase key → actual spellings found in YAML text."""
    by_lower: Dict[str, Set[str]] = {}
    for match in _YAML_KEY.finditer(yaml_text):
        name = match.group(1)
        by_lower.setdefault(name.lower(), set()).add(name)
    return by_lower


def serialize_scalar(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def yaml_key_near_value(yaml_text: str, needle: str, json_key: str) -> List[Tuple[str, int]]:
    """Find YAML key spellings for json_key near occurrences of needle."""
    if not needle or needle.lower() in _WEAK_VALUES and len(needle) < 8:
        return yaml_key_spellings(yaml_text, json_key)
    wanted = json_key.lower()
    hits: List[Tuple[str, int]] = []
    start = 0
    while True:
        index = yaml_text.find(needle, start)
        if index < 0:
            break
        line_start = yaml_text.rfind("\n", 0, index) + 1
        window = yaml_text[max(0, line_start - 8000) : yaml_text.find("\n", index) + 1 or None]
        found: Optional[str] = None
        for line in reversed(window.splitlines()):
            match = _KEY_LINE.match(line)
            if match and match.group(2).lower() == wanted:
                found = match.group(2)
                break
        if found:
            hits.append((found, _line_number(yaml_text, index)))
        start = index + max(len(needle), 1)
    if hits:
        return hits
    return yaml_key_spellings(yaml_text, json_key)


def yaml_key_spellings(yaml_text: str, json_key: str) -> List[Tuple[str, int]]:
    """Case-insensitive search for json_key as a YAML key name."""
    pattern = re.compile(
        r"^[ \t]*(?:-[ \t]+)?(" + re.escape(json_key) + r")[ \t]*:",
        re.I | re.M,
    )
    return [(m.group(1), _line_number(yaml_text, m.start())) for m in pattern.finditer(yaml_text)]


def _walk_scalars(obj: Any, path: Tuple[str, ...]) -> Iterable[Tuple[Tuple[str, ...], Any]]:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            yield from _walk_scalars(value, path + (str(key),))
        return
    if isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _walk_scalars(value, path + (f"[{index}]",))
        return
    yield path, obj


def _path_str(path: Sequence[str]) -> str:
    out = ""
    for part in path:
        if part.startswith("["):
            out += part
        elif not out:
            out = part
        else:
            out += "." + part
    return out


def discover_yaml_keys(
    yaml_text: str,
    api_playbook: Optional[Mapping[str, Any]] = None,
    *,
    task_ids: Optional[Sequence[str]] = None,
    extra_preserve: Sequence[str] = (),
) -> DiscoverResult:
    inventory = inventory_yaml_keys(yaml_text)
    mixed: Set[str] = set()
    for spellings in inventory.values():
        for name in spellings:
            if name != name.lower():
                mixed.add(name)
    mixed.update(extra_preserve)
    mixed.update({"scriptName", "playbookName"})

    renames: Dict[str, str] = {}
    hits: List[ValueHit] = []
    unmatched: List[JsonDict] = []

    # Inventory-only renames: if YAML has exactly one spelling and it is lowercase,
    # camelCase API keys of the same letters should become that spelling.
    for lower, spellings in inventory.items():
        yaml_forms = sorted(spellings)
        if len(yaml_forms) == 1 and yaml_forms[0] == lower:
            # Suggest camelCase variants later from API keys.
            pass

    if api_playbook:
        tasks = playbook_tasks(api_playbook)
        selected = [str(t) for t in task_ids] if task_ids else sorted(tasks.keys(), key=lambda k: (len(k), k))
        for task_id in selected:
            node = tasks.get(task_id)
            if not node:
                continue
            for path, value in _walk_scalars(node, ()):
                needle = serialize_scalar(value)
                if not needle or needle.lower() in _WEAK_VALUES:
                    continue
                ancestor_keys = [
                    part
                    for part in path
                    if part and not part.startswith("[") and part != part.lower()
                ]
                if not ancestor_keys:
                    continue
                for json_key in ancestor_keys:
                    found_keys = yaml_key_near_value(yaml_text, needle, json_key)
                    if not found_keys:
                        found_keys = yaml_key_spellings(yaml_text, json_key)
                    if not found_keys:
                        yaml_forms = inventory.get(json_key.lower()) or set()
                        if yaml_forms:
                            found_keys = [(sorted(yaml_forms)[0], 0)]
                    if not found_keys:
                        unmatched.append(
                            {
                                "task_id": task_id,
                                "json_path": _path_str(path),
                                "json_key": json_key,
                                "value": needle,
                            }
                        )
                        continue
                    yaml_key, line = found_keys[0]
                    if json_key != yaml_key:
                        renames[json_key] = yaml_key
                    hits.append(
                        ValueHit(
                            task_id=task_id,
                            json_path=_path_str(path),
                            json_key=json_key,
                            yaml_key=yaml_key,
                            value=needle if len(needle) < 120 else needle[:117] + "...",
                            line=line,
                        )
                    )

        # Any API mixed-case key seen in YAML inventory.
        def walk_keys(obj: Any) -> Iterable[str]:
            if isinstance(obj, Mapping):
                for key, value in obj.items():
                    yield str(key)
                    yield from walk_keys(value)
            elif isinstance(obj, list):
                for item in obj:
                    yield from walk_keys(item)

        for api_key in walk_keys(api_playbook):
            if api_key == api_key.lower():
                continue
            forms = inventory.get(api_key.lower()) or set()
            if len(forms) == 1:
                yaml_key = next(iter(forms))
                if yaml_key != api_key:
                    renames.setdefault(api_key, yaml_key)

    # Stable sort
    rename_items = dict(sorted(renames.items(), key=lambda item: item[0].lower()))
    hits.sort(key=lambda h: (h.json_key.lower(), h.task_id, h.line))
    return DiscoverResult(
        yaml_keys_lower=sorted({k for spellings in inventory.values() for k in spellings if k == k.lower()}),
        yaml_keys_mixed=sorted(mixed),
        renames=rename_items,
        preserve=sorted(mixed),
        hits=hits,
        unmatched=unmatched,
    )


def load_json_playbook(path: str) -> JsonDict:
    from pathlib import Path

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("playbook"), dict):
        return payload["playbook"]
    if not isinstance(payload, dict):
        raise ValueError(f"JSON playbook must be an object: {path}")
    return payload
