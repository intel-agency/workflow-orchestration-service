# Orchestration Support Services

This repository does not only contain a server and clients. It also contains the event listener, prompt dispatcher, failure notifiers, and trace collection helpers that make orchestration usable in GitHub Actions.

This document covers those supporting services.

The current plan keeps GitHub Actions as the listener. It does not assume a
GitHub App webhook migration.

## What Counts As A Support Service Here

These are the components around orchestration execution rather than the server itself:

- GitHub event listener and dispatcher workflow
- skip logic for irrelevant events
- failure comments posted back to issues
- catch-all failure handling job
- dispatch-issue helpers used to trigger orchestration intentionally
- trace artifact collection and summarization

## The Listener: GitHub Actions Workflow

Primary file:

- `.github/workflows/orchestrator-agent.yml`

There is no standalone webhook listener service in this repository today. The
workflow trigger definition is the listener:

- `issues` with `types: [labeled]`
- `workflow_dispatch`

The workflow decides whether to skip or orchestrate based on the event payload and label semantics.

That remains the active direction for the current migration. The service runtime
is what is changing, not the trigger model.

## Workflow Jobs

### `skip-event`

Purpose:

- explicitly report ignored events instead of silently doing nothing

Current skip cases include:

- actor `traycerai[bot]`
- issue labels that are not orchestration-related and are not `implementation:ready` or `implementation:complete`

### `orchestrate`

Purpose:

- perform the full orchestration run

Key steps:

1. check out the repository
2. assemble the orchestrator prompt
3. log into GHCR and pull the prebuilt devcontainer image
4. install the devcontainer CLI
5. start the devcontainer
6. ensure the opencode server is running
7. restore memory cache
8. execute the orchestrator prompt through the attach client
9. dump logs and collect trace artifacts
10. save the memory cache

This job is the main dispatcher service for GitHub-triggered orchestration.

### `on-failure`

Purpose:

- perform a second-stage failure response if the main orchestration job fails

This job exists because some failures happen before the in-job failure comment step can provide useful context.

## Failure Notifier Services

### In-job failure commenter

Script:

- `scripts/post-failure-comment.sh`

Triggered from the `orchestrate` job when:

- the job fails
- the event is issue-based

What it posts:

- run link
- trigger label
- issue number and title
- actor
- event name/action
- ref and SHA
- likely cause and recovery options

This is the first failure notifier.

### Catch-all failure handler

Script:

- `scripts/on-failure-handler.sh`

Triggered from the separate `on-failure` job.

What it does:

- fetches failed job metadata from the Actions API
- checks whether an issue comment already exists
- posts a fallback issue comment if needed
- emits error annotations into the workflow log

This is the second failure notifier and the backstop when the main job fails early.

## Dispatch Services

### Issue-based dispatcher

Script:

- `scripts/create-dispatch-issue.ps1`

Purpose:

- create a GitHub issue that intentionally triggers an orchestration workflow pattern

This is useful when orchestration is initiated through issue-driven control flow rather than direct local prompting.

Example usage:

```powershell
./scripts/create-dispatch-issue.ps1 -Repo "owner/repo" -Body '/orchestrate-dynamic-workflow
$workflow_name = project-setup'
```

### Test trigger helper

Script:

- `scripts/trigger-orchestrator-test.sh`

Purpose:

- create a test dispatch issue and then query the newest workflow run

This is a lightweight smoke-test helper for the issue-triggered orchestration path.

## Observability Services

### Trace artifact collector

Script:

- `scripts/collect-trace-artifacts.sh`

Purpose:

- copy server and opencode logs out of the devcontainer
- run trace extraction
- assemble artifact files under `/tmp/trace-artifacts`
- print a concise job outcome summary

This script runs from `always()` workflow steps and is intentionally tolerant of partial failures.

### Trace summarizer

Script:

- `scripts/trace-extract.py`

Purpose:

- parse the structured server log
- detect per-session agent activity
- count LLM calls, turns, sequential-thinking calls, and memory calls
- report session-local and global errors

This is the support service that turns raw server logs into a post-mortem artifact.

## Service Boundaries

To avoid confusion, these services are separate concerns:

- The server runs `opencode serve`.
- Clients send prompts.
- The workflow listens for GitHub events.
- Failure notifiers post issue comments and job annotations.
- Observability scripts collect and summarize logs.

If you are debugging "why didn’t orchestration start at all", start with the workflow listener and dispatch services, not the server bootstrapper.

If you are debugging "the server was up but prompt execution stalled", start with the client and trace services.

## Gaps And Current Limitations

- There is no standalone webhook listener or notifier daemon in this repo.
- There is no separate long-running dispatch API service in this repo.
- Failure handling is GitHub Actions based, not service-process based.
- Observability is log-and-artifact oriented rather than metrics/dashboard oriented.

That is the current implemented state, and the docs in this set describe that implemented state rather than the aspirational architecture discussed elsewhere in planning documents.
