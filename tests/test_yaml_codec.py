from __future__ import annotations

from cortex_ps_toolkit.content.yaml_codec import loads_yaml


def test_loads_yaml_quotes_bare_equals_in_simple_fields() -> None:
    text = """
name: Condition PB
tasks:
  "1":
    type: condition
    task:
      name: Check
      conditions:
      - label: equals
        condition:
        - - operator: isEqualString
            left:
              simple: lhs
            right:
              simple: =
"""
    loaded = loads_yaml(text)
    condition = loaded["tasks"]["1"]["task"]["conditions"][0]["condition"][0][0]
    assert condition["right"]["simple"] == "="
