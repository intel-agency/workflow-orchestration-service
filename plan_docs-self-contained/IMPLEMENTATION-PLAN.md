# Standalone Orchestration Service — Implementation Plan

> **Branch:** `feature/standalone-orchestration-service-migration`
> **PR:** [#2 — feat: OS-APOW Standalone Orchestration Service — Phase 0 Foundation](https://github.com/intel-agency/workflow-orchestration-service/pull/2)
> **Created:** 2026-04-02
> **Source Plans:** [Migration Plan](Standalone%20Service%20Migration%20Plan%20-%20workflow-orchestration-service.md) | [Implementation Spec](Application%20Implementation%20Specification%20-%20workflow-orchestration-service%20v1.2.md)

---

## Current State Assessment

### What Exists on the PR Branch (Phase 0 — Partial)

| Artifact | Status | Notes |
|----------|--------|-------|
| `client/src/config.py` | ✅ Implemented | Has bugs: unsafe `int()` casts, `SHELL_BRIDGE_PATH` default may be wrong |
| `client/src/models/work_item.py` | ✅ Implemented | Copied from plan_docs, production-ready |
| `client/src/queue/github_queue.py` | ✅ Implemented | Copied from plan_docs, production-ready |
| `client/src/sentinel.py` | ✅ Implemented | Needs remote dispatch adaptation |
| `client/src/notifier.py` | ✅ Implemented | GHAS flagged 3 log injection vulnerabilities |
| `client/pyproject.toml` | ✅ Implemented | |
| `client/requirements.txt` | ✅ Implemented | Duplicate of pyproject.toml deps |
| `scripts/entrypoint.sh` | ✅ Implemented | Server Docker entrypoint |
| `docker-compose.yml` | ✅ Implemented | References non-existent Dockerfiles |
| `requirements.txt` (root) | ✅ Implemented | Server Python deps |

### What's Missing to Complete Phase 0

| Gap | Severity | Details |
|-----|----------|---------|
| **Root `Dockerfile`** | 🔴 Critical | docker-compose.yml references `./Dockerfile` — doesn't exist |
| **`client/Dockerfile`** | 🔴 Critical | docker-compose.yml references `./client/Dockerfile` — doesn't exist |
| **`ORCHESTRATION_ROOT` in scripts** | 🟡 Medium | `devcontainer-opencode.sh` and `assemble-orchestrator-prompt.sh` need `$ORCHESTRATION_ROOT` support |
| **Security fixes** | 🟡 Medium | Log injection in notifier.py, unsafe int casts in config.py |
| **Validation passes** | 🔴 Blocker | `validate.ps1 -All` must pass before Phase 0 gate |

---

## Phase 0 — Foundation & Dockerfile Consolidation

**Goal:** Self-contained server Docker image builds, all files at `/opt/orchestration/`, scripts resolve paths via `$ORCHESTRATION_ROOT`, Python imports succeed.

### Tasks

| # | Task | Agent | Status | Priority |
|---|------|-------|--------|----------|
| P0-T1 | Create root `Dockerfile` with COPY directives for agents, commands, scripts, configs to `/opt/orchestration/` | `devops-engineer` | ❌ Not started | 🔴 P0 |
| P0-T2 | Create `client/Dockerfile` for containerized client | `devops-engineer` | ❌ Not started | 🔴 P0 |
| P0-T3 | Update `devcontainer-opencode.sh` to use `$ORCHESTRATION_ROOT` for path resolution | `developer` | ❌ Not started | 🟡 P0 |
| P0-T4 | Update `assemble-orchestrator-prompt.sh` to use `$ORCHESTRATION_ROOT` for template path | `developer` | ❌ Not started | 🟡 P0 |
| P0-T5 | Fix `client/src/config.py` — safe int parsing, correct `SHELL_BRIDGE_PATH` default | `developer` | ❌ Not started | 🟡 P0 |
| P0-T6 | Fix `client/src/notifier.py` — address log injection vulnerabilities (GHAS alerts) | `security-expert` | ❌ Not started | 🟡 P0 |
| P0-T7 | Run validation: `validate.ps1 -All` passes clean | `qa-test-engineer` | ❌ Not started | 🔴 Gate |

### Acceptance Criteria

- [ ] `docker build -t orchestration-service:test .` exits 0
- [ ] All expected files present at `/opt/orchestration/` inside the image
- [ ] Scripts have `-rwxr-xr-x` permissions
- [ ] `python -c "import fastapi, httpx, pydantic"` succeeds in server container
- [ ] `ORCHESTRATION_ROOT=/opt/orchestration` is set in the image
- [ ] `opencode --version` returns version string inside the container
- [ ] `client/Dockerfile` builds with `docker build -t orchestration-client:test ./client`
- [ ] `docker compose config` validates successfully
- [ ] `validate.ps1 -All` passes clean
- [ ] No GHAS security alerts on the PR

### Validation Commands

```bash
# V0-1: Server image builds
docker build -t orchestration-service:test .

# V0-2: Files exist at expected paths
docker run --rm orchestration-service:test find /opt/orchestration -type f | sort

# V0-3: Scripts are executable
docker run --rm orchestration-service:test ls -la /opt/orchestration/scripts/

# V0-4: Python imports succeed
docker run --rm orchestration-service:test python -c "import fastapi, httpx, pydantic"

# V0-5: ORCHESTRATION_ROOT is set
docker run --rm orchestration-service:test printenv ORCHESTRATION_ROOT

# V0-6: opencode CLI available
docker run --rm orchestration-service:test opencode --version

# V0-7: Client image builds
docker build -t orchestration-client:test ./client

# V0-8: Compose validates
docker compose config

# V0-9: Full validation suite
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```
P0-T1 (root Dockerfile) ──┬──► P0-T3 (script paths)
                           ├──► P0-T4 (script paths)
P0-T2 (client Dockerfile) ┘
P0-T5 (config fixes) ─────────► independent
P0-T6 (notifier fixes) ───────► independent
                    all ───────► P0-T7 (validation gate)
```

---

## Phase 1 — Server: Self-Contained Orchestration Service

**Goal:** Docker image starts `opencode serve`, accepts prompts via `opencode run --attach`, executes agent workflows, exits cleanly.

**Depends on:** Phase 0 complete.

### Tasks

| # | Task | Agent | Priority |
|---|------|-------|----------|
| P1-T1 | Wire `entrypoint.sh` as Docker ENTRYPOINT, add `EXPOSE 4096` to Dockerfile | `devops-engineer` | 🔴 P1 |
| P1-T2 | Validate server health endpoint — `curl :4096` returns response within 30s of start | `qa-test-engineer` | 🟡 P1 |
| P1-T3 | Test canned prompt execution — `opencode run --attach http://127.0.0.1:4096 -p "Respond: OK"` | `qa-test-engineer` | 🟡 P1 |
| P1-T4 | Test container lifecycle — start/stop/restart/kill recovery, no zombie processes | `qa-test-engineer` | 🟡 P1 |
| P1-T5 | Create test fixtures in `test/fixtures/` — noop prompt, agent list, health check | `qa-test-engineer` | 🟢 P1 |

### Acceptance Criteria

- [ ] `docker run -d -p 4096:4096 -e ... orchestration-service:test` starts container
- [ ] `curl http://localhost:4096/` responds within 30 seconds
- [ ] Server PID file exists at `/tmp/opencode-serve.pid`
- [ ] Canned prompt produces agent output and exits 0
- [ ] `docker stop` triggers graceful shutdown (exit 0)
- [ ] `docker start` after stop → server resumes
- [ ] Missing env vars → non-zero exit with clear error message
- [ ] `docker logs` shows opencode serve log output
- [ ] `validate.ps1 -All` passes clean

### Dependency Graph

```
P1-T1 (ENTRYPOINT) ──┬──► P1-T2 (health check)
                      │       └──► P1-T3 (prompt test)
                      └──► P1-T4 (lifecycle test)
P1-T5 (fixtures) ────────► independent (can parallelize)
                all ──────► validation gate
```

---

## Phase 2 — Client: Remote Prompt Script & Session Management

**Goal:** Sentinel polls GitHub for `agent:queued` issues, dispatches prompts to remote server via shell bridge with `-u <server-url>`, manages full issue lifecycle.

**Depends on:** Phase 1 complete.

### Tasks

| # | Task | Agent | Priority |
|---|------|-------|----------|
| P2-T1 | Verify client project structure — imports resolve, `uv pip install -e .` works | `developer` | 🔴 P2 |
| P2-T2 | Adapt `sentinel.py` for remote dispatch — remove `up`/`start` stages, add `-u` flag | `backend-developer` | 🔴 P2 |
| P2-T3 | Add server health check to Sentinel (HTTP GET before dispatch, backoff on failure) | `backend-developer` | 🟡 P2 |
| P2-T4 | Test remote dispatch end-to-end — server + sentinel + test issue lifecycle | `qa-test-engineer` | 🟡 P2 |

### Key Integration Point

The Sentinel calls:

```
devcontainer-opencode.sh prompt -p <instruction> -u <server-url> -d <server-dir>
```

Which invokes:

```
opencode run --attach <server-url> --agent orchestrator "<prompt>"
```

### Acceptance Criteria

- [ ] `cd client && uv pip install -e .` exits 0
- [ ] `python -c "from src.config import *; print(OPENCODE_SERVER_URL)"` prints URL
- [ ] Shell bridge dispatches remotely with `-u` flag
- [ ] Sentinel polls, discovers `agent:queued` issue, claims it, dispatches to server
- [ ] Label lifecycle: `agent:queued` → `agent:in-progress` → `agent:success`/`agent:error`
- [ ] Heartbeat comments posted during long-running prompts
- [ ] `scrub_secrets()` sanitizes all GitHub-posted content
- [ ] Graceful shutdown on SIGTERM — current task finishes, clean exit
- [ ] `validate.ps1 -All` passes clean

### Dependency Graph

```
P2-T1 (verify structure) ──► P2-T2 (remote dispatch) ──► P2-T3 (health check)
                                                              └──► P2-T4 (E2E test)
                                                     all ──────► validation gate
```

---

## Phase 3 — Client: Webhook Handler & Event Routing

**Goal:** FastAPI webhook handler receives GitHub events, triages into WorkItems, supports dual-mode operation (webhook + polling concurrently).

**Depends on:** Phase 2 complete.

### Tasks

| # | Task | Agent | Priority |
|---|------|-------|----------|
| P3-T1 | Expand `notifier.py` — add `issues.labeled`, `pull_request.*`, `workflow_dispatch` handlers | `backend-developer` | 🔴 P3 |
| P3-T2 | Integrate prompt assembly pipeline — reuse `assemble-orchestrator-prompt.sh` from Python | `backend-developer` | 🟡 P3 |
| P3-T3 | Implement dual-mode `main.py` — FastAPI + Sentinel run concurrently via `asyncio.gather` | `backend-developer` | 🔴 P3 |
| P3-T4 | Test webhook rejection (bad HMAC), acceptance (valid events), and ignored (unmapped events) | `qa-test-engineer` | 🟡 P3 |
| P3-T5 | Validate docker-compose brings up both services, client reaches server | `qa-test-engineer` | 🟡 P3 |

### Acceptance Criteria

- [ ] `POST /webhooks/github` with invalid HMAC → HTTP 401
- [ ] `POST /webhooks/github` with valid signed `issues.labeled` → HTTP 200, issue gets `agent:queued`
- [ ] `workflow_dispatch` events create WorkItems with correct TaskType
- [ ] Unknown event/action combos return `{"status": "ignored"}`
- [ ] `GET /health` returns `{"status": "online"}`
- [ ] Assembled prompt matches GitHub Actions workflow output format
- [ ] Dual-mode: both webhook server and sentinel run in same process
- [ ] `docker compose up` starts both services and they communicate
- [ ] `docker compose down` stops both cleanly
- [ ] `validate.ps1 -All` passes clean

### Dependency Graph

```
P3-T1 (event handlers) ──┬──► P3-T2 (prompt assembly)
                          └──► P3-T3 (dual-mode main.py) ──► P3-T4 (webhook tests)
                                                              └──► P3-T5 (compose test)
                                                     all ──────► validation gate
```

---

## Phase 4 — GitHub App Event Source Integration

**Goal:** GitHub App delivers webhook events to the client, replacing the Actions `on: issues` trigger. End-to-end: real GitHub event → webhook → client → server → issue update.

**Depends on:** Phase 3 complete.

### Tasks

| # | Task | Agent | Priority |
|---|------|-------|----------|
| P4-T1 | Create GitHub App specification — permissions, events, webhook URL | `github-expert` | 🔴 P4 |
| P4-T2 | Configure public webhook endpoint — TLS, reverse proxy (ngrok for dev, Caddy/nginx for prod) | `devops-engineer` | 🟡 P4 |
| P4-T3 | Implement idempotency via `X-GitHub-Delivery` tracking | `backend-developer` | 🟡 P4 |
| P4-T4 | End-to-end test — real GitHub events through full lifecycle | `qa-test-engineer` | 🟡 P4 |

### Acceptance Criteria

- [ ] GitHub App created with correct permissions (Issues RW, PRs RW, Contents RW, Metadata R)
- [ ] App installed on target repository
- [ ] Webhook deliveries show HTTP 200 in App settings
- [ ] HMAC verification works with real secret
- [ ] Duplicate deliveries detected and ignored
- [ ] Response time < 10 seconds (async queue addition, not full orchestration)
- [ ] Full lifecycle: create issue with label → queued → in-progress → success
- [ ] `validate.ps1 -All` passes clean

### Dependency Graph

```
P4-T1 (App spec) ──► P4-T2 (endpoint) ──► P4-T4 (E2E test)
P4-T3 (idempotency) ──────────────────────►
                                  all ──────► validation gate
```

---

## Phase 5 — Production Hardening & Observability

**Goal:** Structured logging, resource limits, budget monitoring, operational runbook, monitoring endpoints.

**Depends on:** Phase 4 complete.

### Tasks

| # | Task | Agent | Priority |
|---|------|-------|----------|
| P5-T1 | Structured JSON-L logging for Sentinel and Notifier | `backend-developer` | 🟡 P5 |
| P5-T2 | Docker resource limits and security hardening in docker-compose | `devops-engineer` | 🟡 P5 |
| P5-T3 | Budget monitor — daily cost limit, `agent:stalled-budget` label, sentinel pause | `backend-developer` | 🟡 P5 |
| P5-T4 | Operational runbook at `docs/runbook.md` | `documentation-expert` | 🟢 P5 |
| P5-T5 | Enhanced `/health` endpoint with server status, `/metrics` (Prometheus-compatible) | `devops-engineer` | 🟢 P5 |

### Acceptance Criteria

- [ ] All log output is valid JSON-L, parseable by standard tools
- [ ] Server container capped at 8GB memory, client at 1GB
- [ ] `no-new-privileges` security option set on both containers
- [ ] Budget exceeded → sentinel pauses, issue labeled `agent:stalled-budget`
- [ ] `/health` reflects real server reachability
- [ ] Runbook covers deployment, config, troubleshooting, log analysis, scaling
- [ ] `validate.ps1 -All` passes clean

### Dependency Graph

```
P5-T1 (logging) ──────┬──► P5-T4 (runbook)
P5-T2 (resource limits)┤    └──► P5-T5 (monitoring)
P5-T3 (budget monitor) ┘
                  all ──────► validation gate
```

---

## Overall Execution Sequence

```
Phase 0 (Foundation)        ──► Phase 1 (Server)           ──► Phase 2 (Client Dispatch)
  P0-T1, P0-T2 (parallel)       P1-T1 ──► P1-T2 ──► P1-T3      P2-T1 ──► P2-T2 ──► P2-T3
  P0-T3, P0-T4 (parallel)       P1-T4 (parallel with T2-T3)     P2-T4
  P0-T5, P0-T6 (parallel)       P1-T5 (parallel)
  P0-T7 (gate)                   gate                             gate
      │                              │                                │
      ▼                              ▼                                ▼
Phase 3 (Webhook)           ──► Phase 4 (GitHub App)        ──► Phase 5 (Production)
  P3-T1 ──► P3-T2                P4-T1 ──► P4-T2                 P5-T1, P5-T2, P5-T3
  P3-T3 ──► P3-T4, P3-T5         P4-T3 (parallel)                P5-T4, P5-T5
  gate                            P4-T4 (gate)                    gate
```

**Total tasks: 29** across 6 phases.

### Phase Gate Protocol

Every phase gate requires:
1. All acceptance criteria checked off
2. All validation commands pass
3. `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes clean
4. No regressions in existing functionality
5. No unresolved GHAS security alerts

**Do NOT proceed to the next phase until the current gate passes.**

---

## Agent Assignment Summary

| Phase | Primary Agents | Task Count |
|-------|---------------|------------|
| Phase 0 (Foundation) | `devops-engineer`, `developer`, `security-expert` | 7 |
| Phase 1 (Server) | `devops-engineer`, `qa-test-engineer` | 5 |
| Phase 2 (Client Dispatch) | `developer`, `backend-developer`, `qa-test-engineer` | 4 |
| Phase 3 (Webhook Handler) | `backend-developer`, `qa-test-engineer` | 5 |
| Phase 4 (GitHub App) | `github-expert`, `devops-engineer`, `backend-developer`, `qa-test-engineer` | 4 |
| Phase 5 (Production) | `backend-developer`, `devops-engineer`, `documentation-expert` | 5 |

---

## Risk Register (Top 5)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missing Dockerfiles block all container testing | 🔴 High | P0-T1 and P0-T2 are first priority |
| Shell bridge `-u` remote dispatch fails silently | 🔴 High | Explicit connection test + stderr logging in P2-T2 |
| Credentials leak in agent output | 🔴 Critical | `scrub_secrets()` on all posted content, verified in every phase |
| Log injection via webhook payloads | 🟡 Medium | Sanitize all logged values from external input (P0-T6) |
| Budget runaway during autonomous execution | 🟡 Medium | Budget monitor in P5-T3 with hard daily limit |

---

## Recommended Execution Order (Starting Now)

### Immediate (Complete Phase 0)

1. **P0-T1**: Create root `Dockerfile` — COPY agents, commands, scripts, configs to `/opt/orchestration/`
2. **P0-T2**: Create `client/Dockerfile` — Python 3.12-slim, install deps, expose 8000
3. **P0-T3 + P0-T4**: Update script path references to use `$ORCHESTRATION_ROOT`
4. **P0-T5**: Fix `config.py` safe int parsing
5. **P0-T6**: Fix `notifier.py` log injection
6. **P0-T7**: Run `validate.ps1 -All` — gate

### Then (Phase 1)

1. Wire entrypoint as ENTRYPOINT in Dockerfile
2. Test server health, canned prompts, lifecycle
3. Create test fixtures

### Then (Phase 2-5 sequentially per gate protocol)

Follow the phase ordering above. Each phase builds on the previous and requires its gate to pass before proceeding.

---

## Configuration Reference

19 environment variables — see [Migration Plan §10.4](Standalone%20Service%20Migration%20Plan%20-%20workflow-orchestration-service.md#104-configuration-reference) for full details.

Key variables needed from Phase 0:
- `ZHIPU_API_KEY`, `GH_ORCHESTRATION_AGENT_TOKEN` (server startup)
- `ORCHESTRATION_ROOT` (default `/opt/orchestration`)

Added in Phase 2+:
- `OPENCODE_SERVER_URL`, `GITHUB_TOKEN`, `GITHUB_ORG`, `GITHUB_REPO`
- `WEBHOOK_SECRET`, `SENTINEL_BOT_LOGIN`
