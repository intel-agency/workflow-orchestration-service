# Orchestration Services Documentation

This repository exposes the orchestration stack through a small set of distinct services. The existing quickstart is still the fastest way to get a local run working, but it does not explain the full system surface area.

Use this document set when you need to understand how the pieces fit together, which script is the correct entrypoint, or how the GitHub-triggered services differ from local client usage.

## Service Map

| Area | What it is | Primary entrypoints | Reference |
|------|------------|---------------------|-----------|
| Server | The long-running `opencode serve` process inside the devcontainer | `scripts/start-opencode-server.sh`, `.devcontainer/devcontainer.json` | [orchestration-server.md](./orchestration-server.md) |
| Clients | Ways to send prompts to the server, or bypass it with direct one-shot execution | `scripts/devcontainer-opencode.sh`, `scripts/prompt-direct.sh`, `scripts/prompt-local.ps1`, `run_opencode_prompt.sh` | [orchestration-clients.md](./orchestration-clients.md) |
| Support services | GitHub-triggered listener/dispatcher/failure-notifier behavior around orchestration | `.github/workflows/orchestrator-agent.yml`, `scripts/post-failure-comment.sh`, `scripts/on-failure-handler.sh`, `scripts/create-dispatch-issue.ps1` | [orchestration-support-services.md](./orchestration-support-services.md) |
| Script catalog | Role-based reference for the orchestration scripts in this repo | `scripts/`, root `run_opencode_prompt.sh` | [orchestration-scripts-reference.md](./orchestration-scripts-reference.md) |
| Gap analysis | Current-state gaps and clarified self-hosted runtime constraints | runtime, docs drift, deployment dependencies | [onprem-gap-analysis.md](./onprem-gap-analysis.md) |
| Migration plan | Plan to move the server to a Compose-managed system service | service runtime, compatibility wrappers, image ownership | [server-system-service-plan.md](./server-system-service-plan.md) |

## Reading Order

1. Start with [local-orchestration-quickstart.md](./local-orchestration-quickstart.md) if you want a working local run immediately.
2. Read [orchestration-server.md](./orchestration-server.md) if you need to operate or troubleshoot the server lifecycle.
3. Read [orchestration-clients.md](./orchestration-clients.md) if you need to choose between server-attach, direct mode, PowerShell wrappers, or CI-style prompt dispatch.
4. Read [orchestration-support-services.md](./orchestration-support-services.md) if your question is about GitHub events, dispatch issues, failure comments, or trace artifacts.
5. Read [onprem-gap-analysis.md](./onprem-gap-analysis.md) for the current migration constraints and clarified scope.
6. Read [server-system-service-plan.md](./server-system-service-plan.md) for the system-service migration plan.
7. Use [orchestration-scripts-reference.md](./orchestration-scripts-reference.md) as the script lookup table.

## Important Current-State Notes

- The primary listener in this repository is GitHub Actions, not a standalone webhook server. The `on:` block in `.github/workflows/orchestrator-agent.yml` is the event listener.
- The current server runtime is the devcontainer-based `opencode serve` process. The active migration direction is to make a Compose-managed service the canonical runtime while retaining the current CLI path as a compatibility layer.
- There are two client styles:
  - Server-attach clients that talk to `opencode serve`
  - Direct clients that run `opencode run` as a one-shot process inside the devcontainer
- `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD` are plumbed into the devcontainer environment, but `scripts/start-opencode-server.sh` does not currently enable server-side auth enforcement. Treat the server as unauthenticated unless that gap is closed.
- The current plan keeps GitHub-centric triggers, state, and dynamic workflows. It does not assume a GitHub App webhook migration.
- The quickstart is intentionally task-oriented. The documents in this set are role-oriented and are the right place for configuration, deployment, usage, and script behavior details.
