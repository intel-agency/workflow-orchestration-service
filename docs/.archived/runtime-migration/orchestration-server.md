# Orchestration Server

This document describes the current server side of the orchestration stack: the
`opencode serve` daemon that runs inside the devcontainer and accepts attached
prompt sessions.

The current local CLI flow is functional and worth preserving. The active
migration direction is to move the canonical runtime to a Compose-managed system
service while keeping the current devcontainer interface as a compatibility and
developer workflow layer. See
[server-system-service-plan.md](./server-system-service-plan.md).

## What The Server Is

The server is a long-running `opencode serve` process launched inside the repository devcontainer. It provides a stable process that clients can attach to with `opencode run --attach ...`, which is the mode used by the GitHub Actions orchestrator workflow and by the local server-attach client scripts.

Primary files:

- `.devcontainer/devcontainer.json`
- `scripts/start-opencode-server.sh`
- `scripts/devcontainer-opencode.sh`
- `run_opencode_prompt.sh`

## Runtime Topology

```
host shell / GitHub runner
  -> devcontainer up
  -> devcontainer exec
  -> scripts/start-opencode-server.sh
  -> opencode serve --hostname 0.0.0.0 --port 4096
```

The server itself runs in the container. Most clients live outside the container and either:

- attach to `http://127.0.0.1:4096` from inside the same devcontainer execution flow, or
- rely on forwarded port `4096` from the devcontainer configuration

## How The Server Starts

There are two normal current start paths:

1. Automatic start from `.devcontainer/devcontainer.json`
   - `postStartCommand` runs `bash ./scripts/start-opencode-server.sh`
2. Explicit start from the lifecycle wrapper
   - `bash scripts/devcontainer-opencode.sh start`

The bootstrapper is idempotent. If a healthy server is already running, it exits without restarting it. If a stale PID file exists or the process is dead, it cleans up and starts a fresh server.

## Bootstrapper Behavior

`scripts/start-opencode-server.sh` is the authoritative server bootstrapper. It does the following:

- Exports `GH_TOKEN` from `GH_ORCHESTRATION_AGENT_TOKEN` when available
- Enables `OPENCODE_EXPERIMENTAL=1`
- Sets server defaults:
  - `OPENCODE_SERVER_HOSTNAME=0.0.0.0`
  - `OPENCODE_SERVER_PORT=4096`
  - `OPENCODE_SERVER_LOG=/tmp/opencode-serve.log`
  - `OPENCODE_SERVER_PIDFILE=/tmp/opencode-serve.pid`
  - `OPENCODE_SERVER_READY_TIMEOUT_SECS=30`
- Verifies that `opencode` is on `PATH`
- Reuses an already-healthy server when possible
- Kills stale server processes when the PID file is present but the server is unhealthy
- Starts the server with `setsid` so it survives `devcontainer exec` session teardown
- Waits for readiness by polling `http://127.0.0.1:<port>/`

The server is started with:

```bash
opencode serve \
  --hostname "$OPENCODE_SERVER_HOSTNAME" \
  --port "$OPENCODE_SERVER_PORT" \
  --log-level "$OPENCODE_SERVER_LOG_LEVEL" \
  --print-logs
```

## Configuration

### Required environment for real orchestration work

These values are expected to be present in the container environment for normal runs:

- `GH_ORCHESTRATION_AGENT_TOKEN`
- `ZHIPU_API_KEY`
- `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY`

Optional provider variables:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY` on the host, mapped to `GOOGLE_GENERATIVE_AI_API_KEY` in the container

### Server-specific environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENCODE_SERVER_HOSTNAME` | `0.0.0.0` | Bind address used by `opencode serve` |
| `OPENCODE_SERVER_PORT` | `4096` | Server port |
| `OPENCODE_SERVER_LOG` | `/tmp/opencode-serve.log` | Server log file |
| `OPENCODE_SERVER_PIDFILE` | `/tmp/opencode-serve.pid` | PID file for the daemon |
| `OPENCODE_SERVER_READY_TIMEOUT_SECS` | `30` | Readiness wait timeout |
| `OPENCODE_SERVER_LOG_LEVEL` | `INFO` | Server log verbosity |

### Devcontainer environment passthrough

`.devcontainer/devcontainer.json` forwards these relevant values from the host:

- `GH_ORCHESTRATION_AGENT_TOKEN`
- `ZHIPU_API_KEY`
- `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY` -> `GOOGLE_GENERATIVE_AI_API_KEY`
- `OPENCODE_SERVER_HOSTNAME`
- `OPENCODE_SERVER_PORT`
- `OPENCODE_SERVER_USERNAME`
- `OPENCODE_SERVER_PASSWORD`

## Operations

### Start or reconnect the devcontainer

```bash
bash scripts/devcontainer-opencode.sh up
```

### Ensure the server is running

```bash
bash scripts/devcontainer-opencode.sh start
```

### Check status

```bash
bash scripts/devcontainer-opencode.sh status
```

The `status` command reports:

- devcontainer state
- server PID and readiness
- memory database presence
- last 20 lines of the server log

### Stop the container

```bash
bash scripts/devcontainer-opencode.sh stop
```

### Full teardown

```bash
bash scripts/devcontainer-opencode.sh down
```

## Logs, State, And Files

| File | Meaning |
|------|---------|
| `/tmp/opencode-serve.pid` | PID of the server daemon |
| `/tmp/opencode-serve.log` | Server log output from `opencode serve --print-logs` |
| `.memory/memory.db` | SQLite-backed memory database bind-mounted from the repo workspace |

The server-side memory DB is configured through the devcontainer `remoteEnv` and lives in the repository workspace, so it is visible both on the host and in the container.

## Deployment Modes

### 1. Local developer workstation

This is the best-supported mode in this repository:

- host machine runs Docker and devcontainer CLI
- devcontainer hosts the orchestration runtime
- clients dispatch locally

### 2. GitHub Actions ephemeral runtime

`.github/workflows/orchestrator-agent.yml` provisions the devcontainer on a runner, starts the server, then attaches a prompt session to it. This is the primary automation path.

### 3. Standalone container entrypoint support

`scripts/entrypoint.sh` exists for image-style startup where the orchestration code is mounted or baked into a container image. In this repository, it is supporting infrastructure rather than the main documented deployment path.

### Planned direction

The intended destination is:

- repo-owned image build in this repository
- a Compose-managed service as the primary long-running runtime
- current devcontainer scripts preserved as a compatibility path rather than the
  primary hosting model

## Security And Network Caveats

- The bootstrapper binds the server to `0.0.0.0`, so it is not limited to loopback inside the container.
- Port `4096` is forwarded by the devcontainer configuration.
- The repo currently does not document or enforce TLS termination for the server.
- `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD` are passed through the devcontainer config, but the bootstrapper does not presently pass auth flags to `opencode serve`. That means server-side authentication is not actually enforced by this repo today.

If you expose the service beyond a trusted local environment, add network controls outside this repository or close the auth gap first.

## Failure Modes

Common server-side failures:

- image pull failure or devcontainer startup failure
- missing provider credentials in the host environment
- stale server PID file after an interrupted session
- provider/model failures surfaced in `/tmp/opencode-serve.log`
- session attach failures from clients when the server is down

First checks:

```bash
bash scripts/devcontainer-opencode.sh status
bash scripts/devcontainer-opencode.sh start
```

If the server still does not come up, read `/tmp/opencode-serve.log` from the status output or from an interactive `devcontainer exec` session.
