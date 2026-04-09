#!/usr/bin/env bash
set -euo pipefail

# entrypoint.sh — Docker ENTRYPOINT for the orchestration server container.
#
# Exports GitHub auth tokens, validates required env vars, starts the
# opencode server, and tails the log for Docker log collection.

ORCHESTRATION_ROOT="${ORCHESTRATION_ROOT:-/opt/orchestration}"
cd "$ORCHESTRATION_ROOT"

# Export GitHub auth under all names that tools (gh CLI, MCP, opencode) may read
if [[ -n "${GH_ORCHESTRATION_AGENT_TOKEN:-}" ]]; then
    export GH_TOKEN="$GH_ORCHESTRATION_AGENT_TOKEN"
    export GITHUB_TOKEN="$GH_ORCHESTRATION_AGENT_TOKEN"
    export GITHUB_PERSONAL_ACCESS_TOKEN="$GH_ORCHESTRATION_AGENT_TOKEN"
fi

export OPENCODE_EXPERIMENTAL=1

# Validate required secrets
for var in ZHIPU_API_KEY GH_ORCHESTRATION_AGENT_TOKEN; do
    if [[ -z "${!var:-}" ]]; then
        echo "FATAL: $var is not set" >&2
        exit 1
    fi
done

echo "[entrypoint] Starting opencode server..."
bash "$ORCHESTRATION_ROOT/scripts/start-opencode-server.sh"

echo "[entrypoint] Server started on port ${OPENCODE_SERVER_PORT:-4096}. Tailing log..."
exec tail -f /tmp/opencode-serve.log
