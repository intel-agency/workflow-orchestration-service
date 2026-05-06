# Orchestration Scripts Reference

This is the role-based script catalog for the orchestration services in this repository.

## Server Lifecycle

| Script | Role | Typical caller |
|--------|------|----------------|
| `scripts/start-opencode-server.sh` | Starts or reuses the `opencode serve` daemon inside the devcontainer | `postStartCommand`, `scripts/devcontainer-opencode.sh`, `scripts/entrypoint.sh` |
| `scripts/devcontainer-opencode.sh` | Host-side lifecycle wrapper for `up`, `start`, `prompt`, `status`, `stop`, `down` | local users, CI workflow |
| `scripts/entrypoint.sh` | Container-style entrypoint that exports auth and starts the server | image-style deployment support |

## Prompt Dispatch Clients

| Script | Role | Uses server? |
|--------|------|--------------|
| `scripts/prompt-direct.sh` | Direct one-shot `opencode run` in the devcontainer | No |
| `scripts/prompt-local.ps1` | PowerShell local wrapper around the attach client | Yes |
| `run_opencode_prompt.sh` | Low-level attach runner with auth validation, watchdog, and log streaming | Yes |
| `scripts/prompt.ps1` | Low-level PowerShell runner for `opencode run` | Optional |

## Prompt Assembly

| Script | Role | Main use |
|--------|------|----------|
| `scripts/assemble-orchestrator-prompt.sh` | GitHub Actions prompt assembler using workflow event metadata | CI / workflow runs |
| `scripts/assemble-local-prompt.sh` | Local freeform or fixture-based prompt generator | local testing |

## Environment And Setup

| Script | Role |
|--------|------|
| `scripts/setup-local-env.sh` | Creates `.env` from `.env.example`, validates required vars, optionally logs into GHCR |
| `scripts/install-dev-tools.ps1` | Installs local validation tooling used by `scripts/validate.ps1` |
| `scripts/validate.ps1` | Shared local/CI validation entrypoint |

## GitHub Triggering And Failure Handling

| Script | Role |
|--------|------|
| `scripts/create-dispatch-issue.ps1` | Creates a GitHub issue to dispatch an orchestration workflow pattern |
| `scripts/trigger-orchestrator-test.sh` | Creates a test dispatch issue and prints the newest workflow run |
| `scripts/post-failure-comment.sh` | Posts a detailed issue comment from the main workflow job on failure |
| `scripts/on-failure-handler.sh` | Backstop failure handler job that gathers context and posts a catch-all issue comment |

## Observability And Trace Analysis

| Script | Role |
|--------|------|
| `scripts/collect-trace-artifacts.sh` | Copies logs out of the devcontainer and builds workflow trace artifacts |
| `scripts/trace-extract.py` | Parses structured server logs into a session-oriented trace report |

## Administrative Orchestration Helpers

These are related to repo workflow control rather than core server/client execution:

| Script | Role |
|--------|------|
| `scripts/import-labels.ps1` | Syncs labels from `.github/.labels.json` |
| `scripts/create-project.ps1` | Creates project boards |
| `scripts/create-milestones.ps1` | Creates milestones from plan docs |
| `scripts/common-auth.ps1` | Shared GitHub auth helper for PowerShell scripts |
| `scripts/gh-auth.ps1` | GitHub auth helper with PAT and interactive flows |

## Which Script Should I Use?

### I want the simplest local prompt run

Use:

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/prompt-direct.sh -p "say hello"
```

### I want to match GitHub Actions behavior

Use:

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/devcontainer-opencode.sh start
bash scripts/devcontainer-opencode.sh prompt -p "say hello"
```

### I want to send a prompt from PowerShell

Use:

```powershell
./scripts/prompt-local.ps1 -Prompt "say hello"
```

### I want to simulate an issue-triggered event locally

Use:

```bash
bash scripts/assemble-local-prompt.sh -f test/fixtures/issues-opened.json
bash scripts/devcontainer-opencode.sh prompt -f .assembled-orchestrator-prompt.md
```

### I want to debug a workflow failure

Start with:

- `scripts/post-failure-comment.sh`
- `scripts/on-failure-handler.sh`
- `scripts/collect-trace-artifacts.sh`
- `scripts/trace-extract.py`

## Key Environment Variables By Script Family

| Script family | Important variables |
|---------------|---------------------|
| server lifecycle | `OPENCODE_SERVER_HOSTNAME`, `OPENCODE_SERVER_PORT`, `OPENCODE_SERVER_LOG`, `OPENCODE_SERVER_PIDFILE` |
| provider auth | `ZHIPU_API_KEY`, `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` |
| GitHub auth | `GH_ORCHESTRATION_AGENT_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_PERSONAL_ACCESS_TOKEN` |
| attach auth | `OPENCODE_AUTH_USER`, `OPENCODE_AUTH_PASS` |
| memory | `MCP_MEMORY_SQLITE_PATH`, `MCP_MEMORY_STORAGE_BACKEND`, `MCP_MEMORY_SQLITE_PRAGMAS` |

## Notes On Script Boundaries

- `scripts/devcontainer-opencode.sh` is the host-side entrypoint, not the server itself.
- `run_opencode_prompt.sh` is where most attach-session behavior lives.
- `scripts/prompt-direct.sh` bypasses the server entirely.
- `scripts/assemble-orchestrator-prompt.sh` is workflow-oriented, while `scripts/assemble-local-prompt.sh` is local-usage-oriented.
- `scripts/post-failure-comment.sh` and `scripts/on-failure-handler.sh` are notifier services, not orchestration clients.
