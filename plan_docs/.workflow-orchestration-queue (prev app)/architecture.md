# Architecture — OS-APOW (workflow-orchestration-service)

## System Overview

OS-APOW (Orchestration Service — Autonomous Pipeline for Orchestrated Workflows) is a headless agentic orchestration platform that transforms GitHub Issues into autonomous execution orders fulfilled by specialized AI agents. The system replaces interactive AI coding with a persistent, event-driven infrastructure.

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub (State Layer)                          │
│  Issues ─► Labels ─► Milestones ─► Projects ─► Pull Requests   │
└──────┬──────────────────────────────────┬───────────────────────┘
       │ Webhooks (Phase 2)               │ REST API (Phase 1)
       ▼                                  ▼
┌──────────────┐                  ┌───────────────────┐
│  The Ear     │                  │  The Sentinel     │
│  (Notifier)  │──── Queue ──────│  (Orchestrator)   │
│  FastAPI     │                  │  Python Async     │
└──────────────┘                  └────────┬──────────┘
                                           │ Shell Bridge
                                           ▼
                                  ┌───────────────────┐
                                  │  The Hands        │
                                  │  (Opencode Worker) │
                                  │  DevContainer      │
                                  └───────────────────┘
```

## Core Components

### A. Work Event Notifier — "The Ear" (Phase 2)

- **Stack:** Python 3.12, FastAPI, Pydantic
- **Role:** Secure webhook ingestion gateway
- **Key Features:**
  - HMAC SHA-256 signature verification on all incoming payloads
  - Intelligent event triage — maps GitHub payloads to unified WorkItem objects
  - Sub-second task ingestion via push-based webhook model

### B. Work Queue — "The State"

- **Implementation:** GitHub Issues + Labels + Milestones
- **Philosophy:** "Markdown as a Database" — transparent, auditable, version-controlled
- **State Machine (Labels):**
  - `agent:queued` → Task validated, awaiting Sentinel pickup
  - `agent:in-progress` → Sentinel claimed task (issue assigned as distributed lock)
  - `agent:reconciling` → Stale task recovery after crash
  - `agent:success` → Terminal success (PR created, tests passed)
  - `agent:error` → Technical failure (stderr posted as comment)
  - `agent:infra-failure` → Container/environment failure
  - `agent:stalled-budget` → Daily cost threshold exceeded

### C. Sentinel Orchestrator — "The Brain" (Phase 1)

- **Stack:** Python (async), PowerShell Core, Docker CLI
- **Role:** Persistent supervisor managing Worker lifecycle
- **Key Features:**
  - Polling-based task discovery (60s interval, jittered exponential backoff on rate limits)
  - Assign-then-verify locking pattern using GitHub Assignees
  - Shell-bridge execution via `devcontainer-opencode.sh`
  - Heartbeat comments every 5 minutes during long-running tasks
  - Structured JSONL logging with unique `SENTINEL_ID` per instance

### D. Opencode Worker — "The Hands"

- **Stack:** opencode CLI, LLM (GLM-5/Claude), DevContainer
- **Role:** Isolated execution environment for AI-driven code generation
- **Key Features:**
  - High-fidelity DevContainer (bit-for-bit identical to developer environment)
  - Markdown-based instruction modules (`local_ai_instruction_modules/`)
  - Local test suite execution before PR submission
  - Network-isolated Docker bridge (no host subnet access)
  - Resource-constrained (2 CPUs, 4GB RAM)

## Data Flow (Happy Path)

1. **Stimulus:** User opens GitHub Issue using application-plan template
2. **Notification:** GitHub webhook hits the Notifier (FastAPI) — *or* Sentinel polls for `agent:queued` labels
3. **Triage:** Payload verified, WorkItem manifest generated, `agent:queued` label applied
4. **Claim:** Sentinel discovers task, assigns itself (assign-then-verify), labels `agent:in-progress`
5. **Dispatch:** Sentinel calls `devcontainer-opencode.sh prompt` with structured context
6. **Execute:** Worker runs instruction modules, generates/modifies code, runs tests
7. **Deliver:** Worker pushes branch, creates PR linking back to issue
8. **Close:** Sentinel labels issue `agent:success`, removes `agent:in-progress`

## Security Model

| Boundary | Control |
|----------|---------|
| Webhook ingestion | HMAC SHA-256 signature validation |
| Credential management | Ephemeral in-memory env vars, destroyed on container exit |
| Log sanitization | `scrub_secrets()` strips PATs, Bearer tokens, API keys before posting |
| Network isolation | Worker containers on segregated bridge network |
| Concurrency | Assign-then-verify distributed locking via GitHub Assignees |

## Key Architectural Decisions

- **ADR-07:** Shell-bridge execution exclusively via `devcontainer-opencode.sh` (no Python Docker SDK)
- **ADR-08:** Polling-first resiliency — webhooks are an optimization, not a requirement
- **ADR-09:** Provider-agnostic `ITaskQueue` interface for future ticket system portability

## Phased Rollout

| Phase | Name | Focus |
|-------|------|-------|
| 0 | Seeding | Manual bootstrap from template, environment setup |
| 1 | The Sentinel (MVP) | Polling engine, shell-bridge dispatch, status feedback |
| 2 | The Ear | FastAPI webhook receiver, push-based ingestion |
| 3 | Deep Orchestration | Hierarchical decomposition, autonomous PR review correction |
