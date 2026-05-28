#!/usr/bin/env bash
# Placeholder entrypoint — Phase 3 replaces with the full FastAPI startup.
set -euo pipefail

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "workflow-orchestration-client — FastAPI client (port 8000)"
    echo "Default: python3 -m uvicorn src.notifier:app --host 0.0.0.0 --port 8000"
    exit 0
fi

# Pass-through: run arbitrary commands (e.g., python3 -c "import ...")
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Default: start the uvicorn placeholder server
exec python3 -m uvicorn src.notifier:app --host 0.0.0.0 --port 8000
