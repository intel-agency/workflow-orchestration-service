# Orchestration Clients

This repository has multiple ways to send work to the orchestration stack. They
are not interchangeable, and most confusion comes from not knowing which client
mode is intended for a given task.

The current client flows remain valid. The active migration direction is to keep
these user-facing flows, especially `scripts/devcontainer-opencode.sh`, while
moving the primary runtime toward a Compose-managed service. See
[server-system-service-plan.md](./server-system-service-plan.md).

## Client Modes

| Client mode | Primary script | Uses server? | Best for |
|-------------|----------------|--------------|----------|
| Direct bash client | `scripts/prompt-direct.sh` | No | Local one-shot runs, simplest path, least moving parts |
| Server-attach bash client | `scripts/devcontainer-opencode.sh prompt` | Yes | Parity with GitHub Actions orchestration flow |
| Local PowerShell wrapper | `scripts/prompt-local.ps1` | Yes | Windows/PowerShell local usage |
| In-container attach runner | `run_opencode_prompt.sh` | Yes | CI and low-level attach execution |
| In-container PowerShell runner | `scripts/prompt.ps1` | Optional | In-container PowerShell attach or direct runs |
| Prompt assembly helper | `scripts/assemble-local-prompt.sh` | No, prepares input | Local fixture-based or freeform prompt creation |

## Choosing The Right Client

Use `scripts/prompt-direct.sh` when:

- you are working locally
- you do not need a long-running server session
- you want the fewest failure points

Use `scripts/devcontainer-opencode.sh prompt` or `scripts/prompt-local.ps1` when:

- you want to mirror the GitHub Actions attach flow
- you need the server lifecycle separated from prompt dispatch
- you want to keep the devcontainer/server warm across multiple prompts
- you want parity with the current CLI path that is expected to survive the
  service migration as a compatibility layer

Use `run_opencode_prompt.sh` when:

- you are inside the devcontainer or CI
- you need the lowest-level attach runner
- you need the built-in GitHub token validation and watchdog behavior

## Direct Client

### Script

`scripts/prompt-direct.sh`

### What it does

Runs `opencode run` directly inside the devcontainer as a one-shot process. No background server is required.

### Typical usage

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/prompt-direct.sh -p "Say hello and confirm you are operational."
```

From a file:

```bash
bash scripts/prompt-direct.sh -f test/fixtures/prompts/hello-world.txt
```

With a different model:

```bash
bash scripts/prompt-direct.sh -p "list open issues" -m zai-coding-plan/glm-4.7-flash
```

### Required environment

- `GH_ORCHESTRATION_AGENT_TOKEN`
- `ZHIPU_API_KEY`
- `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY`

### Notes

- This is the recommended local client because it avoids server lifecycle issues.
- The devcontainer still must already be running.
- The script derives the container working directory as `/workspaces/<repo-name>`.

## Server-Attach Bash Client

### Script

`scripts/devcontainer-opencode.sh`

### What it does

Provides the lifecycle wrapper for:

- `up`
- `start`
- `prompt`
- `status`
- `stop`
- `down`

The `prompt` subcommand dispatches to `run_opencode_prompt.sh` inside the devcontainer and attaches to the running server.

### Typical flow

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/devcontainer-opencode.sh start
bash scripts/devcontainer-opencode.sh prompt -p "Summarize the open issues."
```

Prompt from file:

```bash
bash scripts/devcontainer-opencode.sh prompt -f .assembled-orchestrator-prompt.md
```

### Required environment for `prompt`

- `ZHIPU_API_KEY`
- `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY`
- `GH_ORCHESTRATION_AGENT_TOKEN`

### Notes

- This is the client path that most closely matches the CI workflow.
- The wrapper forwards the required env vars into the devcontainer execution context.
- If `OPENCODE_SERVER_DIR` is not set, the client uses `/workspaces/<repo-name>`.

## PowerShell Local Client

### Script

`scripts/prompt-local.ps1`

### What it does

PowerShell wrapper around the server-attach flow. By default it:

1. starts the devcontainer/server if needed
2. dispatches the prompt via `scripts/devcontainer-opencode.sh prompt`

### Typical usage

```powershell
./scripts/prompt-local.ps1 -Prompt "list open issues and summarize them"
./scripts/prompt-local.ps1 -File test/fixtures/prompts/create-epic.txt
./scripts/prompt-local.ps1 -Prompt "say hello" -SkipStart
```

### Parameters

| Parameter | Purpose |
|-----------|---------|
| `-Prompt` | Inline prompt text |
| `-File` | Prompt file path |
| `-ServerUrl` | Attach URL, default `http://127.0.0.1:4096` |
| `-ServerDir` | Server-side working directory |
| `-SkipStart` | Skip the start step if the server is already up |

## Low-Level Attach Runner

### Script

`run_opencode_prompt.sh`

### What it does

This is the low-level attach client used by CI and by the bash lifecycle wrapper. It:

- reads prompt text from `-f` or `-p`
- validates required provider credentials
- requires `GH_ORCHESTRATION_AGENT_TOKEN`
- exports GitHub auth under all expected variable names
- validates GitHub API access and required scopes
- optionally embeds basic auth credentials into the attach URL
- runs `opencode run --attach ...`
- applies the watchdog and trace streaming behavior

### Why it matters

If you need to understand:

- why CI fails after a long idle period
- why token scope validation fails before prompt execution
- where attach URL auth is assembled
- how client/server logs are surfaced

this is the script to read.

## PowerShell Low-Level Runner

### Script

`scripts/prompt.ps1`

### What it does

This is a small PowerShell runner for `opencode run`. It can be used with or without `-Attach`, and supports optional basic-auth URL embedding via `-Username` and `-Password`.

This is lower-level than `scripts/prompt-local.ps1` and does not manage the devcontainer lifecycle for you.

## Prompt Preparation Clients

### Local prompt assembler

`scripts/assemble-local-prompt.sh` prepares prompts for local testing in two modes:

- freeform mode: `-p "your prompt"`
- fixture mode: `-f test/fixtures/issues-opened.json`

Freeform usage:

```bash
bash scripts/assemble-local-prompt.sh -p "say hello"
```

Fixture usage:

```bash
bash scripts/assemble-local-prompt.sh -f test/fixtures/issues-opened.json
```

Output defaults to `.assembled-orchestrator-prompt.md`.

### CI prompt assembler

`scripts/assemble-orchestrator-prompt.sh` is the GitHub Actions prompt assembler. It expects workflow-provided event metadata and uses the prompt template in `.github/workflows/prompts/orchestrator-agent-prompt.md`.

Use it when you want the same prompt structure the workflow uses.

## Recommended Usage Patterns

### Best default for local development

```bash
bash scripts/setup-local-env.sh
set -a; source .env; set +a
bash scripts/devcontainer-opencode.sh up
bash scripts/prompt-direct.sh -p "Say hello and confirm you are operational."
```

### Best parity with CI

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/devcontainer-opencode.sh start
bash scripts/assemble-local-prompt.sh -f test/fixtures/issues-opened.json
bash scripts/devcontainer-opencode.sh prompt -f .assembled-orchestrator-prompt.md
```

### Best Windows/PowerShell path

```powershell
./scripts/prompt-local.ps1 -Prompt "say hello"
```

## Troubleshooting Client Choice

- If the server dies between `start` and `prompt`, use `scripts/prompt-direct.sh` for local work.
- If you need GitHub Actions parity, do not use direct mode alone; use the attach flow.
- If the issue is around token validation, attach URLs, watchdog timeouts, or log streaming, inspect `run_opencode_prompt.sh`.
- If the issue is only local prompt authoring, use `scripts/assemble-local-prompt.sh` and keep the execution path separate.
