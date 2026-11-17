#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8091}"

if [[ "${1:-}" == "--test" ]]; then
  echo "Running SkillForge AI test suite..."
  python3 -m unittest discover -s tests -v
  exit 0
fi

if [[ "${1:-}" == "--cli" ]]; then
  shift
  python3 cli.py "$@"
  exit 0
fi

if [[ "${1:-}" == "--mcp-test" ]]; then
  python3 mcp_server.py --self-test
  exit 0
fi

echo "Starting SkillForge AI Studio on http://127.0.0.1:${PORT} ..."
exec python3 server.py --host 127.0.0.1 --port "${PORT}"
