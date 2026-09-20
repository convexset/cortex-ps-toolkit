#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export CORTEX_PS_DATA_DIR="${CORTEX_PS_DATA_DIR:-$ROOT/data}"
export CORTEX_PS_DEBUG="${CORTEX_PS_DEBUG:-1}"

PORT="${CORTEX_PS_PORT:-8770}"
HOST="${CORTEX_PS_HOST:-127.0.0.1}"

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port ${PORT} is already in use." >&2
  echo "  Use a different port: CORTEX_PS_PORT=8771 $0" >&2
  exit 1
fi

echo "Cortex PS Toolkit → http://${HOST}:${PORT}/"
echo "  Profile context UI enabled (index patched at serve time)"
exec python3 -m cortex_ps_toolkit.serve_with_profile_context \
  --host "${HOST}" --port "${PORT}" --reload --debug "$@"
