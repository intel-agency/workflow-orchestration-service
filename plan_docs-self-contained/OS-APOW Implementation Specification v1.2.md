# OS-APOW Standalone Orchestration Service — Implementation Specification v2.0

## Project

**Repository:** `intel-agency/workflow-orchestration-service`  
**Branch:** `feature/standalone-orchestration-service-migration`  
**PR:** [#2 — feat: OS-APOW Standalone Orchestration Service — Phase 0 Foundation](https://github.com/intel-agency/workflow-orchestration-service/pull/2)  
**Date:** 2026-03-29

---

## Plan Document References

### Canonical Plans (current, authoritative)

| Document | Path | Purpose |
|---|---|---|
| **Migration & Implementation Plan** | [`OS-APOW-standalone-service-migration-plan.md`](OS-APOW-standalone-service-migration-plan.md) | Full 6-phase migration plan with architecture, code inventory, task breakdowns, validation plans, agent assignment matrix, risk register, and file migration map |

### Existing Project Plan Docs (seeded at clone time)

These documents are expected to exist in the parent `plan_docs/` directory, seeded by the `create-repo-from-slug.ps1` workflow:

| Document | Expected Location | Purpose |
|---|---|---|
| Architecture Guide v3.2 | `plan_docs/OS-APOW Architecture Guide v3.2.md` | System-level diagrams, security boundaries, 4-pillar overview |
| Development Plan v4.2 | `plan_docs/OS-APOW Development Plan v4.2.md` | Phased roadmap, guiding principles, user stories, risk mitigations |
| Architecture doc | `plan_docs/architecture.md` | System overview, data flow, security model |
| Tech Stack doc | `plan_docs/tech-stack.md` | Python, FastAPI, opencode, Docker, uv |

### Related Documentation

| Document | Expected Location | Purpose |
|---|---|---|
| Memory Server Migration Plan | `docs/memory-server-migration-plan.md` | MCP memory server migration (server-memory → mcp-memory-service) |

---

## Overview

Migrate the orchestration workflow agent from a GitHub Actions-embedded model to a **standalone, self-hosted, networked client/server service**. The server runs the full orchestration stack (opencode CLI, agents, MCP servers) inside a Docker image. The client is a Python service that receives GitHub events via webhooks and dispatches prompts to the remote server.

### Key Insight — Existing Code Coverage

The codebase already provides substantial implementation. The migration is primarily an **integration and packaging** effort:

| Component | Coverage | Location |
|---|---|---|
| Sentinel Orchestrator (polling, claiming, heartbeats, shell bridge) | ~90% | `plan_docs/orchestrator_sentinel.py` |
| Webhook Notifier (FastAPI, HMAC verification, event triage) | ~80% | `plan_docs/notifier_service.py` |
| Unified Work Item Model (Pydantic, credential scrubbing) | ~95% | `plan_docs/src/models/work_item.py` |
| GitHub Queue (ITaskQueue, claim, heartbeat, status updates) | ~85% | `plan_docs/src/queue/github_queue.py` |
| Shell Bridge (devcontainer lifecycle, prompt dispatch) | 100% | `scripts/devcontainer-opencode.sh` |
| OpenCode Server Bootstrap | 100% | `scripts/start-opencode-server.sh` |
| OpenCode Prompt Runner (auth, validation, model dispatch) | 100% | `run_opencode_prompt.sh` |

### End-State Architecture

```
GitHub App (webhooks) → Orchestration Client (FastAPI + Sentinel, :8000)
                          → TCP :4096 →
                        Orchestration Server (opencode serve, Docker, :4096)
```

See the [Migration Plan §1–2](OS-APOW-standalone-service-migration-plan.md#1-executive-summary) for the full architecture diagrams, component responsibilities, network topology, and data flow.

---

## Execution Plan

### Step 1: Phase 0 — Foundation & Dockerfile Consolidation

**Source:** [Migration Plan §4](OS-APOW-standalone-service-migration-plan.md#4-phase-0--foundation--dockerfile-consolidation)

**Objective:** Update the Dockerfile to include all necessary files for a self-contained orchestration service image.

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P0-T1 | Define server directory structure (`/opt/orchestration/`) | `devops-engineer` | None |
| P0-T2 | Add COPY directives to Dockerfile for agents, commands, scripts, configs | `devops-engineer` | P0-T1 |
| P0-T3 | Update hardcoded paths in scripts to use `$ORCHESTRATION_ROOT` | `developer` | P0-T2 |
| P0-T4 | Install Python dependencies (FastAPI, httpx, Pydantic, uvicorn) in image | `devops-engineer` | P0-T2 |

**Validation:** Docker image builds, all files present at expected paths, scripts executable, Python imports succeed, `ORCHESTRATION_ROOT` set. See [Migration Plan §4.2](OS-APOW-standalone-service-migration-plan.md#42-phase-0--validation-plan) for full validation matrix (V0-1 through V0-7).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

### Step 2: Phase 1 — Server: Self-Contained Orchestration Service

**Source:** [Migration Plan §5](OS-APOW-standalone-service-migration-plan.md#5-phase-1--server-self-contained-orchestration-service)

**Objective:** Verify the Docker image can start opencode server, accept prompts, execute orchestration workflows, and exit cleanly.

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P1-T1 | Create server entrypoint script (`entrypoint.sh`) with env validation, auth export, `opencode serve` bootstrap | `devops-engineer` | Phase 0 |
| P1-T2 | Validate server health endpoint (curl `:4096`, PID file, idempotent start) | `qa-test-engineer` | P1-T1 |
| P1-T3 | Test canned prompt execution via `opencode run --attach` | `qa-test-engineer` | P1-T2 |
| P1-T4 | Test container lifecycle (start/stop/restart/kill recovery) | `qa-test-engineer` | P1-T1 |
| P1-T5 | Create test fixtures for canned prompts in `test/fixtures/` | `qa-test-engineer` | None |

**Validation:** Server starts and listens on `:4096`, canned prompts execute, container lifecycle is clean, missing env vars fail fast. See [Migration Plan §5.2](OS-APOW-standalone-service-migration-plan.md#52-phase-1--validation-plan) (V1-1 through V1-8).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

### Step 3: Phase 2 — Client: Remote Prompt Script & Session Management

**Source:** [Migration Plan §6](OS-APOW-standalone-service-migration-plan.md#6-phase-2--client-remote-prompt-script--session-management)

**Objective:** Build the client-side Sentinel Orchestrator that polls GitHub for queued issues and dispatches prompts to the remote server.

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P2-T1 | Create client project structure (`client/src/`, copy Python modules from `plan_docs/`) | `developer` | Phase 1 |
| P2-T2 | Create centralized config module (`client/src/config.py`) | `developer` | P2-T1 |
| P2-T3 | Adapt Sentinel for remote server dispatch (remove `up`/`start` stages, add `-u <server-url>`) | `backend-developer` | P2-T1, P2-T2 |
| P2-T4 | Add server health check to Sentinel (HTTP GET before dispatch) | `backend-developer` | P2-T3 |
| P2-T5 | Test remote prompt dispatch end-to-end (server + sentinel + test issue) | `qa-test-engineer` | P2-T3, P2-T4 |

**Key integration point:** The Sentinel calls `devcontainer-opencode.sh prompt -p <instruction> -u <server-url>` which invokes `opencode run --attach <server-url>`. This is the same shell bridge, now dispatching remotely.

**Validation:** Client installs, config loads, shell bridge dispatches remotely, Sentinel polls/claims/dispatches, heartbeats post, credentials scrubbed. See [Migration Plan §6.2](OS-APOW-standalone-service-migration-plan.md#62-phase-2--validation-plan) (V2-1 through V2-11).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

### Step 4: Phase 3 — Client: Webhook Handler & Event Routing

**Source:** [Migration Plan §7](OS-APOW-standalone-service-migration-plan.md#7-phase-3--client-webhook-handler--event-routing)

**Objective:** Integrate the FastAPI webhook handler into the client. Receives GitHub events, triages into WorkItems, and supports dual-mode operation (webhook + polling).

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P3-T1 | Adapt notifier service for client integration (import paths, event coverage, shared queue) | `backend-developer` | Phase 2 |
| P3-T2 | Add event type handlers (`issues.labeled`, `pull_request.*`, `workflow_dispatch`) | `backend-developer` | P3-T1 |
| P3-T3 | Integrate prompt assembly pipeline (reuse `assemble-orchestrator-prompt.sh`) | `backend-developer` | P3-T2 |
| P3-T4 | Implement dual-mode operation (FastAPI + Sentinel concurrent in `main.py`) | `backend-developer` | P3-T1, P2-T3 |
| P3-T5 | Create client Dockerfile | `devops-engineer` | P3-T4 |
| P3-T6 | Create/update docker-compose.yml for local dev (server + client) | `devops-engineer` | P3-T5, P1-T1 |

**Validation:** Webhook rejects bad signatures, accepts valid events, prompt assembly matches Actions workflow output, dual-mode runs concurrently, docker-compose orchestrates both services. See [Migration Plan §7.2](OS-APOW-standalone-service-migration-plan.md#72-phase-3--validation-plan) (V3-1 through V3-11).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

### Step 5: Phase 4 — GitHub App Event Source Integration

**Source:** [Migration Plan §8](OS-APOW-standalone-service-migration-plan.md#8-phase-4--github-app-event-source-integration)

**Objective:** Create and configure a GitHub App that delivers repository events to the client's webhook endpoint, replacing the GitHub Actions `on: issues` trigger.

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P4-T1 | Create GitHub App specification (permissions, events, webhook URL) | `github-expert` | Phase 3 |
| P4-T2 | Configure public webhook delivery endpoint (TLS, reverse proxy) | `devops-engineer` | P4-T1 |
| P4-T3 | Test event delivery pipeline (real GitHub events → client → server → issue update) | `qa-test-engineer` | P4-T1, P4-T2 |
| P4-T4 | Implement webhook retry handling (idempotency via delivery ID tracking) | `backend-developer` | P3-T1 |

**Validation:** GitHub App delivers webhooks, HMAC verification works with real secrets, idempotency on retry, end-to-end with real events, response under 10s. See [Migration Plan §8.2](OS-APOW-standalone-service-migration-plan.md#82-phase-4--validation-plan) (V4-1 through V4-7).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

### Step 6: Phase 5 — Production Hardening & Observability

**Source:** [Migration Plan §9](OS-APOW-standalone-service-migration-plan.md#9-phase-5--production-hardening--observability)

**Objective:** Harden both server and client for production use with structured logging, resource limits, budget monitoring, and operational documentation.

| Task | Description | Agent | Dependencies |
|---|---|---|---|
| P5-T1 | Structured JSON-L logging for Sentinel and Notifier | `backend-developer` | P2-T3 |
| P5-T2 | Docker resource limits and security hardening (cgroup limits, read-only FS, no-new-privileges) | `devops-engineer` | P3-T6 |
| P5-T3 | Cost guardrails / budget monitor (`agent:stalled-budget` label) | `backend-developer` | P2-T3 |
| P5-T4 | Operational runbook (`docs/runbook.md`) | `documentation-expert` | P5-T1, P5-T2 |
| P5-T5 | Monitoring and alerting endpoints (`/health` with server status, `/metrics`) | `devops-engineer` | P5-T1 |

**Validation:** JSON-L logs parse, resource limits enforced, budget monitor pauses sentinel, health check reflects real state, runbook accurate. See [Migration Plan §9.2](OS-APOW-standalone-service-migration-plan.md#92-phase-5--validation-plan) (V5-1 through V5-8).

**Gate:** `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean.

---

## Cross-Cutting Concerns

Detailed in [Migration Plan §10](OS-APOW-standalone-service-migration-plan.md#10-cross-cutting-concerns):

- **Security:** HMAC webhook verification, `scrub_secrets()` on all posted content, container isolation, minimum token scopes
- **Error handling:** Health check failures → backoff, missed webhooks → polling recovery, subprocess timeouts → kill + label, Sentinel crash → restart + reconcile
- **Testing strategy:** Unit (pytest), integration (shell bridge + docker), end-to-end (real GitHub events), load (concurrent issues)
- **Configuration:** 19 environment variables documented with defaults — see [Migration Plan §10.4](OS-APOW-standalone-service-migration-plan.md#104-configuration-reference)

---

## Agent Assignment Summary

Full matrix in [Migration Plan §11](OS-APOW-standalone-service-migration-plan.md#11-agent-assignment-matrix).

| Phase | Primary Agents | Task Count |
|---|---|---|
| Phase 0 (Foundation) | `devops-engineer`, `developer` | 4 |
| Phase 1 (Server) | `devops-engineer`, `qa-test-engineer` | 5 |
| Phase 2 (Client Dispatch) | `developer`, `backend-developer`, `qa-test-engineer` | 5 |
| Phase 3 (Webhook Handler) | `backend-developer`, `devops-engineer` | 6 |
| Phase 4 (GitHub App) | `github-expert`, `devops-engineer`, `backend-developer`, `qa-test-engineer` | 4 |
| Phase 5 (Production) | `backend-developer`, `devops-engineer`, `documentation-expert` | 5 |
| **Total** | | **29 tasks** |

Maximum delegation depth: 2 (orchestrator → specialist → sub-specialist).

---

## Risk Register

Top risks from [Migration Plan §12](OS-APOW-standalone-service-migration-plan.md#12-risk-register):

| ID | Risk | Mitigation |
|---|---|---|
| R1 | Shell bridge remote dispatch fails silently | Explicit connection test before dispatch; log all stderr |
| R6 | Credentials leak in agent output | `scrub_secrets()` on all GitHub-posted content |
| R7 | Budget runaway during autonomous execution | Budget monitor with daily limit; `agent:stalled-budget` halts processing |
| R10 | Prompt injection via crafted issue body | Only process verified GitHub App payloads; never execute raw user input |

---

## Implementation Sequence

```
Pre-Tasks (PT-1, PT-2, PT-3)  ← ALL COMPLETE
         │
         ▼
Phase 0 (Foundation)      → Phase 1 (Server)         → Phase 2 (Client Dispatch)
  P0-T1 → P0-T2 →            P1-T1 → P1-T2 →            P2-T1 → P2-T2 →
  P0-T3 → P0-T4              P1-T3 → P1-T4 →            P2-T3 → P2-T4 →
  │                           P1-T5                       P2-T5
  └── VALIDATE ───────────────└── VALIDATE ───────────────└── VALIDATE
                                                                  │
Phase 3 (Webhook)         → Phase 4 (GitHub App)     → Phase 5 (Production)
  P3-T1 → P3-T2 →            P4-T1 → P4-T2 →            P5-T1 → P5-T2 →
  P3-T3 → P3-T4 →            P4-T3 → P4-T4              P5-T3 → P5-T4 →
  P3-T5 → P3-T6                                          P5-T5
  │                           │                           │
  └── VALIDATE ───────────────└── VALIDATE ───────────────└── VALIDATE
```

Each phase gate requires `pwsh -NoProfile -File ./scripts/validate.ps1 -All` to pass clean before proceeding.

---

## Language & Frameworks

- **Python 3.12+** — Sentinel, Webhook Notifier, models, queue
- **FastAPI** — Webhook handler (async, Pydantic, auto-OpenAPI)
- **Pydantic** — Data schemas (WorkItem, TaskType, WorkItemStatus)
- **httpx** — Async HTTP client for GitHub API
- **uvicorn** — ASGI server
- **uv** — Python package manager (Rust-based, fast)
- **Bash/PowerShell** — Shell bridge scripts, auth, validation
- **Docker** — Server container, client container (optional), compose

---

## Deliverables

1. **Self-contained orchestration server Docker image** — opencode serve + agents + MCP servers, listens on `:4096`
2. **Orchestration client Python service** — FastAPI webhook handler + Sentinel polling loop, listens on `:8000`
3. **Docker Compose** — orchestrates both services for local and production use
4. **GitHub App configuration** — delivers repository events as webhooks
5. **Operational runbook** — deployment, configuration, troubleshooting, monitoring
6. **Test suite** — unit, integration, end-to-end, covering the full event → orchestration → result lifecycle
