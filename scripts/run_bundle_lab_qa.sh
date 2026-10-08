#!/usr/bin/env bash
# Bundle copy lab QA — preview matrix (default) and optional live execute.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Bundle lab QA: preview matrix =="
python3 -m pytest tests/integration/test_bundle_copy_modes_lab.py tests/integration/test_bundle_lab_qa.py -m integration -v "$@"

if [[ "${CORTEX_PS_BUNDLE_LAB_EXECUTE:-}" == "1" ]]; then
  echo "== Bundle lab QA: live execute (copy-as-new script) =="
  python3 -m pytest tests/integration/test_bundle_lab_qa.py::test_bundle_execute_copy_as_new_script_env_gated -m integration -v "$@"
else
  echo "Tip: CORTEX_PS_BUNDLE_LAB_EXECUTE=1 $0 — run one live copy-as-new script execute test"
  echo "Tip: add CORTEX_PS_BUNDLE_LAB_CLEANUP=1 with EXECUTE to delete the renamed script on target"
fi

echo "== Copy-components preview (lab) =="
python3 -m pytest tests/integration/test_copy_components_lab.py -m integration -v "$@"
