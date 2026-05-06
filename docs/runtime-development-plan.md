# Orchestration Runtime - Development Plan

> Status: Ready for orchestrated implementation planning  
> Scope authority: `docs/orchestration-runtime.md`  
> Format reference: `plan_docs-self-contained/IMPLEMENTATION-PLAN.md`  
> Target implementer: `orchestrator-agent` with delegated specialist agents  
> Created: 2026-05-06

This document is the detailed phased development plan for implementing the
standalone orchestration runtime. It is written for automated development by the
orchestrator agent and bounded delegate agents.

`docs/orchestration-runtime.md` is the architecture and scope source of truth.
The older self-contained implementation plans are useful references, but they do
not override the current decisions documented there.

## Execution Model For Orchestrator Agents

The orchestrator owns sequencing, delegation, integration, validation gates, and
phase-level status. Delegated agents own bounded implementation tasks with clear
write scopes.

Every delegated task must define:

| Field | Required content |
|-------|------------------|
| Owner role | Specialist role expected to implement or verify the task |
| Inputs | Existing files, configuration, docs, fixtures, or commands to inspect |
| Expected outputs | Files changed, behavior added, tests added, or report produced |
| Likely files | Expected write scope; avoid overlapping writes across parallel tasks |
| Acceptance criteria | Concrete checks that prove the task is complete |
| Validation commands | Exact commands the delegate or integrator must run |
| Dependencies | Prior tasks or phase gates that must complete first |

Implementation rules for autonomous execution:

- Prefer small, verifiable tasks over broad multi-file assignments.
- Parallelize only when write scopes are disjoint.
- Do not proceed past a phase gate until all phase acceptance criteria and
  validation commands pass.
- Treat CI, tests, coverage, Docker builds, and image publishing as part of the
  implementation work, not as cleanup after feature work.
- Preserve the existing prompt command surface unless a later approved plan
  explicitly changes it.

## Current State Assessment

### Implemented Or Partially Implemented

| Artifact | Status | Notes |
|----------|--------|-------|
| `scripts/start-opencode-server.sh` | Implemented | Starts/reuses `opencode serve`, writes logs, waits for readiness. |
| `scripts/entrypoint.sh` | Implemented | Container-style entrypoint that exports auth and starts the server. |
| `scripts/devcontainer-opencode.sh prompt` | Implemented | Supports prompt dispatch through `-p`, `-f`, `-u`, and `-d`. |
| `run_opencode_prompt.sh` | Implemented | Low-level attach runner with auth setup and watchdog behavior. |
| `docker-compose.yml` | Partial | Defines intended server/client services but references missing Dockerfiles. |
| `client/src/*` | Partial | Notifier, sentinel, queue, config, and work-item model exist but need validation and adaptation. |
| `docs/orchestration-runtime.md` | Implemented | Canonical runtime scope, decisions, architecture, and open questions. |

### Blocking Gaps

| Gap | Severity | Details |
|-----|----------|---------|
| Missing root `Dockerfile` | Critical | `docker-compose.yml` references `./Dockerfile`, but no root Dockerfile is tracked. |
| Missing `client/Dockerfile` | Critical | `docker-compose.yml` references `./client/Dockerfile`, but no client Dockerfile is tracked. |
| `ORCHESTRATION_ROOT` support | High | Runtime scripts still assume repo/devcontainer paths in places that need image-safe defaults. |
| Runnable Compose path | Critical | Compose cannot be the primary runtime until images, env files, volumes, health checks, and logs are complete. |
| Workspace/clone manager | High | Target repos must be cloned/managed inside the standalone runtime. |
| GitHub Actions bridge | High | Workflow-to-local/LAN server connectivity is undecided. |
| Validation prerequisites | Medium | Pester tests require `gh` on `PATH`; other local tools may be skipped if not installed. |

## Phase 0 - Foundation And Image Contract

Goal: build a self-contained server image with all required orchestration files
under `/opt/orchestration`.

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P0-T1 | Create root Dockerfile and define `/opt/orchestration` layout | `devops-engineer` | `Dockerfile` | None |
| P0-T2 | Copy agents, commands, scripts, prompts, config, and root runner into image | `devops-engineer` | `Dockerfile` | P0-T1 |
| P0-T3 | Set `ORCHESTRATION_ROOT=/opt/orchestration` and ensure image startup uses it | `devops-engineer` | `Dockerfile`, `scripts/entrypoint.sh` | P0-T1 |
| P0-T4 | Ensure copied shell scripts are executable in the image | `devops-engineer` | `Dockerfile` | P0-T2 |
| P0-T5 | Include required runtime tools and Python dependencies | `devops-engineer` | `Dockerfile`, `requirements.txt` | P0-T1 |
| P0-T6 | Create `client/Dockerfile` for the existing Python client scaffold | `devops-engineer` | `client/Dockerfile` | None |
| P0-T7 | Fix obvious client config defects discovered during image work | `developer` | `client/src/config.py`, `client/pyproject.toml` | P0-T6 |
| P0-T8 | Fix logging injection risks in webhook/client code | `backend-developer` | `client/src/notifier.py` | None |
| P0-T9 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P0-T1 through P0-T8 |

### Acceptance Criteria

- [ ] `docker build -t orchestration-service:test .` exits 0.
- [ ] `docker build -t orchestration-client:test ./client` exits 0.
- [ ] `docker compose config` validates successfully.
- [ ] `ORCHESTRATION_ROOT=/opt/orchestration` is set in the server image.
- [ ] Expected files exist under `/opt/orchestration`, including `.opencode/`,
      `opencode.json`, `AGENTS.md`, `scripts/`, and `run_opencode_prompt.sh`.
- [ ] Shell scripts copied into the image are executable.
- [ ] Required tools are available where required: `opencode`, `gh`, `git`,
      `pwsh`, `bash`, `curl`, `python`, `uv`, `bun`, and `node`.
- [ ] Python imports succeed for required server/client dependencies.
- [ ] No secrets or local `.env` contents are baked into either image.
- [ ] No unresolved critical/high static-analysis or security findings are left
      in files touched during the phase.

### Validation Commands

```bash
docker build -t orchestration-service:test .
docker build -t orchestration-client:test ./client
docker compose config
docker run --rm orchestration-service:test printenv ORCHESTRATION_ROOT
docker run --rm orchestration-service:test find /opt/orchestration -maxdepth 3 -type f | sort
docker run --rm orchestration-service:test ls -la /opt/orchestration/scripts/
docker run --rm orchestration-service:test opencode --version
docker run --rm orchestration-service:test gh --version
docker run --rm orchestration-service:test python -c "import fastapi, httpx, pydantic"
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```text
P0-T1 ──► P0-T2 ──► P0-T3 ──► P0-T4
   │         │
   │         └──► P0-T5
   ├────────────► P0-T6 ──► P0-T7
   ├────────────► P0-T8
   └──────────────────────────────► P0-T9 phase gate
```

## Phase 1 - Standalone Opencode Server

Goal: the server container starts `opencode serve` and accepts attached prompts.

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P1-T1 | Wire `scripts/entrypoint.sh` as the server image entrypoint | `devops-engineer` | `Dockerfile`, `scripts/entrypoint.sh` | Phase 0 |
| P1-T2 | Expose and document port `4096` | `devops-engineer` | `Dockerfile`, `docker-compose.yml` | P1-T1 |
| P1-T3 | Validate health endpoint and readiness timeout behavior | `qa-test-engineer` | tests/fixtures as needed | P1-T1 |
| P1-T4 | Validate PID and log behavior | `qa-test-engineer` | tests/fixtures as needed | P1-T1 |
| P1-T5 | Test canned prompt through `opencode run --attach` | `qa-test-engineer` | `test/fixtures/prompts/` | P1-T3 |
| P1-T6 | Test stop, start, restart, and kill recovery behavior | `qa-test-engineer` | tests/fixtures as needed | P1-T1 |
| P1-T7 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P1-T1 through P1-T6 |

### Acceptance Criteria

- [ ] Server container starts within configured timeout when required env vars are present.
- [ ] Missing required env vars fail fast with clear non-secret error messages.
- [ ] `curl http://localhost:4096/` responds after startup.
- [ ] `/tmp/opencode-serve.pid` exists inside the container.
- [ ] `/tmp/opencode-serve.log` exists and contains startup logs.
- [ ] Canned prompt through `opencode run --attach` exits 0.
- [ ] `docker stop` exits cleanly.
- [ ] Restart recovers the server.
- [ ] Forced process termination is recovered by the bootstrapper or container restart policy.
- [ ] `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes or only fails for documented missing local tools unrelated to the change.

### Validation Commands

```bash
docker run --rm orchestration-service:test /bin/bash -lc 'printenv ORCHESTRATION_ROOT && opencode --version'
docker run -d --name orchestration-service-test -p 4096:4096 --env-file .env orchestration-service:test
curl -fsS http://localhost:4096/
docker exec orchestration-service-test test -f /tmp/opencode-serve.pid
docker exec orchestration-service-test test -f /tmp/opencode-serve.log
docker logs orchestration-service-test
docker stop orchestration-service-test
docker rm orchestration-service-test
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```text
Phase 0 gate ──► P1-T1 ──┬──► P1-T2
                          ├──► P1-T3 ──► P1-T5
                          ├──► P1-T4
                          └──► P1-T6
                                      └──► P1-T7 phase gate
```

## Phase 2 - Compose Runtime

Goal: `docker compose up -d` runs the server as the primary local/LAN runtime.

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P2-T1 | Update Compose service contract for the server image | `devops-engineer` | `docker-compose.yml` | Phase 1 |
| P2-T2 | Add env-file support and document required variables | `devops-engineer` | `docker-compose.yml`, `.env.example`, docs | P2-T1 |
| P2-T3 | Add memory, log, and workspace volume mounts | `devops-engineer` | `docker-compose.yml` | P2-T1 |
| P2-T4 | Add health check and restart policy | `devops-engineer` | `docker-compose.yml` | P2-T1 |
| P2-T5 | Add local status/log guidance for Compose runtime | `documentation-expert` | docs/runtime docs | P2-T1 |
| P2-T6 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P2-T1 through P2-T5 |

### Acceptance Criteria

- [ ] `docker compose config` exits 0.
- [ ] `docker compose up -d orchestration-server` starts the server.
- [ ] Compose service health becomes green.
- [ ] Memory database persists across restart.
- [ ] Logs persist across restart.
- [ ] Workspace volume persists across restart.
- [ ] Server port is configurable through env.
- [ ] Compose teardown does not delete named volumes unless explicitly requested.
- [ ] Local operator commands for status and logs are documented.

### Validation Commands

```bash
docker compose config
docker compose up -d orchestration-server
docker compose ps
docker compose logs orchestration-server
curl -fsS http://localhost:${OPENCODE_SERVER_PORT:-4096}/
docker compose restart orchestration-server
docker compose ps
docker compose down
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```text
Phase 1 gate ──► P2-T1 ──┬──► P2-T2
                          ├──► P2-T3
                          ├──► P2-T4
                          └──► P2-T5
                                      └──► P2-T6 phase gate
```

## Phase 3 - Script Compatibility

Goal: preserve existing prompt interfaces while allowing a Compose-backed
runtime.

Stable interfaces:

- `scripts/devcontainer-opencode.sh prompt`
- `run_opencode_prompt.sh`
- `-p`, `-f`, `-u`, `-d`

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P3-T1 | Add `ORCHESTRATION_ROOT` path handling where needed | `developer` | `scripts/devcontainer-opencode.sh`, `scripts/assemble-orchestrator-prompt.sh` | Phase 2 |
| P3-T2 | Preserve the devcontainer lifecycle path | `developer` | `scripts/devcontainer-opencode.sh` | P3-T1 |
| P3-T3 | Support remote attach URL flow against Compose runtime | `developer` | `scripts/devcontainer-opencode.sh`, `run_opencode_prompt.sh` | P3-T1 |
| P3-T4 | Preserve inline and file prompt modes | `developer` | `scripts/devcontainer-opencode.sh`, `run_opencode_prompt.sh` | P3-T1 |
| P3-T5 | Document default runtime behavior and override knobs | `documentation-expert` | docs/runtime docs | P3-T1 through P3-T4 |
| P3-T6 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P3-T1 through P3-T5 |

### Acceptance Criteria

- [ ] Existing devcontainer prompt flow still works.
- [ ] Remote attach URL flow works against a running Compose server.
- [ ] `-p` inline prompt mode works.
- [ ] `-f` prompt-file mode works.
- [ ] `-u` server URL override works.
- [ ] `-d` server-side directory override works.
- [ ] No caller-facing flag regression is introduced.
- [ ] Error messages are actionable and do not expose secrets.
- [ ] Script behavior is documented for both devcontainer and Compose-backed usage.

### Validation Commands

```bash
bash scripts/devcontainer-opencode.sh prompt -p "Respond: OK" -u http://127.0.0.1:4096 -d /opt/orchestration
bash scripts/devcontainer-opencode.sh prompt -f test/fixtures/prompts/hello-world.txt -u http://127.0.0.1:4096 -d /opt/orchestration
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```text
Phase 2 gate ──► P3-T1 ──┬──► P3-T2
                          ├──► P3-T3
                          ├──► P3-T4
                          └──► P3-T5
                                      └──► P3-T6 phase gate
```

## Phase 4 - Repository Workspace Manager

Goal: target repositories are cloned and managed inside the standalone runtime.

Default policy:

- `ORCHESTRATION_WORKSPACE_ROOT=/opt/orchestration/workspaces`
- persistent clone reuse with fetch/reset
- isolated worktrees only when concurrency requires it

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P4-T1 | Define repo/ref input contract for prompt/event metadata | `backend-developer` | scripts, docs, fixtures | Phase 3 |
| P4-T2 | Implement checkout resolution under workspace root | `developer` | new script or existing prompt wrapper | P4-T1 |
| P4-T3 | Implement persistent clone reuse with fetch/reset | `developer` | workspace manager script | P4-T2 |
| P4-T4 | Wire resolved checkout to `OPENCODE_SERVER_DIR` / `-d` | `developer` | prompt wrapper scripts | P4-T2 |
| P4-T5 | Define cleanup and concurrency policy | `documentation-expert` | docs/runtime docs | P4-T2 |
| P4-T6 | Add workspace manager tests and fixtures | `qa-test-engineer` | `test/`, fixtures | P4-T2 through P4-T4 |
| P4-T7 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P4-T1 through P4-T6 |

### Acceptance Criteria

- [ ] A target repo can be cloned into the workspace root.
- [ ] An existing clone can be reused safely.
- [ ] Fetch/reset can move the checkout to the requested ref.
- [ ] Opencode executes from the resolved checkout.
- [ ] The checkout is visible through container shell and bind-mounted workspace paths.
- [ ] Failed clone/fetch produces clear failure output.
- [ ] No repo checkout happens only in a hidden GitHub Actions runner path.
- [ ] Cleanup and concurrency policy is documented before bridge work begins.

### Validation Commands

```bash
docker compose exec orchestration-server bash -lc 'printenv ORCHESTRATION_WORKSPACE_ROOT'
docker compose exec orchestration-server bash -lc 'find "${ORCHESTRATION_WORKSPACE_ROOT:-/opt/orchestration/workspaces}" -maxdepth 3 -type d | sort'
bash scripts/devcontainer-opencode.sh prompt -p "Inspect the current repository and report the git remote." -u http://127.0.0.1:4096 -d /opt/orchestration/workspaces/<owner>/<repo>
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

### Dependency Graph

```text
Phase 3 gate ──► P4-T1 ──► P4-T2 ──┬──► P4-T3
                                    ├──► P4-T4
                                    ├──► P4-T5
                                    └──► P4-T6
                                                └──► P4-T7 phase gate
```

## Phase 5 - GitHub Actions Bridge

Goal: GitHub Actions remains the trigger and prompt assembly layer, but calls a
local/LAN runtime instead of starting the server in every workflow run.

Candidate bridge options:

- Tailscale
- ngrok
- simple authenticated HTTP or SSH bridge

The bridge choice must be made after the local Compose runtime works.

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P5-T1 | Evaluate bridge options against local/LAN deployment constraints | `devops-engineer` | docs/report | Phase 4 |
| P5-T2 | Choose bridge and define minimal auth model | `devops-engineer` | docs/runtime docs, `.env.example` | P5-T1 |
| P5-T3 | Update workflow execution target while preserving prompt assembly | `github-expert` | `.github/workflows/orchestrator-agent.yml`, scripts | P5-T2 |
| P5-T4 | Preserve failure comment and log behavior | `github-expert` | workflow/scripts | P5-T3 |
| P5-T5 | Add bridge failure tests or dry-run checks | `qa-test-engineer` | `test/`, fixtures | P5-T3 |
| P5-T6 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P5-T1 through P5-T5 |

### Acceptance Criteria

- [ ] `workflow_dispatch` can send a prompt to the local/LAN server.
- [ ] `issues.labeled` can send a prompt to the local/LAN server.
- [ ] Bridge failures fail visibly in workflow logs.
- [ ] Failure comment behavior remains clear for issue-triggered runs.
- [ ] Server-side logs remain collectable for diagnostics.
- [ ] Workflow does not assume GitHub-hosted runners can directly reach private LAN.
- [ ] Bridge auth secret is not logged.
- [ ] Workflow action `uses:` references remain full-SHA pinned with version comments.

### Validation Commands

```bash
pwsh -NoProfile -File ./scripts/validate.ps1 -Lint
pwsh -NoProfile -File ./scripts/validate.ps1 -Test
gh workflow run orchestrator-agent.yml --field prompt="Respond: OK"
gh run list --limit 5
```

### Dependency Graph

```text
Phase 4 gate ──► P5-T1 ──► P5-T2 ──► P5-T3 ──┬──► P5-T4
                                              └──► P5-T5
                                                         └──► P5-T6 phase gate
```

## Phase 6 - Operator Observation

Goal: operators can inspect the same filesystem that opencode is modifying.

Default phase-one observation paths:

- `docker compose exec orchestration-server bash`
- `docker compose logs -f orchestration-server`
- bind-mounted logs and workspace volumes

VS Code Insiders tunnel rule:

- include only if it is a small optional sibling daemon
- disable by default
- defer if it adds process supervision, auth, image, or runtime complexity

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P6-T1 | Document default shell/log/workspace observation commands | `documentation-expert` | docs/runtime docs | Phase 4 |
| P6-T2 | Verify bind-mounted workspace visibility | `qa-test-engineer` | test artifacts only | P6-T1 |
| P6-T3 | Evaluate VS Code Insiders tunnel complexity | `devops-engineer` | docs/report | Phase 4 |
| P6-T4 | If low complexity, plan optional tunnel env vars and startup path | `devops-engineer` | docs/runtime docs | P6-T3 |
| P6-T5 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P6-T1 through P6-T4 |

### Acceptance Criteria

- [ ] Operator can inspect active workspace through container shell.
- [ ] Operator can inspect server logs through Compose.
- [ ] Operator can inspect persisted workspace/log volumes from the host.
- [ ] Observation path uses the same filesystem as opencode.
- [ ] VS Code tunnel, if included, is opt-in and disabled by default.
- [ ] VS Code tunnel is deferred if it materially complicates the runtime.

### Validation Commands

```bash
docker compose exec orchestration-server bash -lc 'pwd && ls -la /opt/orchestration'
docker compose logs --tail=100 orchestration-server
docker compose exec orchestration-server bash -lc 'find "${ORCHESTRATION_WORKSPACE_ROOT:-/opt/orchestration/workspaces}" -maxdepth 2 -type d | sort'
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

## Phase 7 - Phase-Two Hardening

Goal: harden the runtime after the service contract is stable.

### Tasks

| # | Task | Owner role | Likely files | Dependencies |
|---|------|------------|--------------|--------------|
| P7-T1 | Enforce auth on exposed server/bridge interfaces | `devops-engineer` | scripts, Compose, docs | Phase 5 |
| P7-T2 | Define TLS/reverse-proxy/firewall guidance | `devops-engineer` | docs/runbook or runtime docs | P7-T1 |
| P7-T3 | Add resource limits and container hardening | `devops-engineer` | `docker-compose.yml` | Phase 2 |
| P7-T4 | Add structured logging and monitoring strategy | `backend-developer` | client/server scripts/docs | Phase 5 |
| P7-T5 | Create operational runbook | `documentation-expert` | docs/runbook.md | P7-T1 through P7-T4 |
| P7-T6 | Run phase validation and record results | `qa-test-engineer` | test artifacts only | P7-T1 through P7-T5 |

### Acceptance Criteria

- [ ] Auth is enforced wherever runtime access is exposed beyond localhost.
- [ ] TLS/reverse-proxy/firewall guidance is documented.
- [ ] Compose resource limits are set for server and optional client services.
- [ ] Health/metrics endpoint strategy is documented or implemented.
- [ ] Runbook covers deployment, configuration, troubleshooting, logs, backups,
      upgrades, and rollback.
- [ ] Critical/high security findings are resolved or explicitly deferred with
      rationale.

## Deferred Later Phases

The older self-contained migration plans include additional phases that are not
current implementation scope. They remain useful future work.

### Python Sentinel Client

Future value:

- poll GitHub for queued work
- claim issues with assign-then-verify locking
- dispatch prompts through the shell bridge
- post heartbeats and terminal status comments

Current-phase constraints:

- preserve `devcontainer-opencode.sh prompt`
- preserve `-p`, `-f`, `-u`, and `-d`
- keep server URL and server directory configurable
- avoid hardwiring assumptions that only work from GitHub Actions.

### FastAPI Webhook Handler

Future value:

- accept signed GitHub webhook events
- triage events into work items
- provide `/health`
- enqueue work for sentinel or direct dispatch

Current-phase constraints:

- keep prompt assembly separable from GitHub Actions
- keep workspace manager source-agnostic
- keep event metadata rich enough to resolve target repo and ref.

### GitHub App Event Source

Future value:

- replace or supplement GitHub Actions event triggers
- deliver real webhook events to the self-hosted client
- support retry/idempotency through GitHub delivery IDs

Current-phase constraints:

- do not make GitHub App migration current scope
- avoid bridge designs that prevent later webhook adoption
- keep service names, ports, and auth variables stable.

### Production Observability Stack

Future value:

- structured logs
- metrics
- budget guardrails
- alerting
- operational runbook

Current-phase constraints:

- preserve log volume structure
- expose enough health status for future monitoring
- avoid burying server logs only inside ephemeral workflow output.

## Validation And CI Plan

### Local Validation

The full local validation command remains:

```powershell
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

Known prerequisite:

- `gh` must be installed and on `PATH` for Pester tests that exercise GitHub CLI
  dry-run paths.

Phase-specific commands are listed in each phase. They are additive; they do
not replace the full validation command.

### Automated Tests

Required automated test coverage:

| Area | Minimum tests |
|------|---------------|
| Shell scripts | prompt assembly, image tag logic, watchdog I/O, script compatibility |
| PowerShell scripts | Pester tests for dispatch/setup scripts |
| Python models | work-item parsing, task classification, secret scrubbing |
| Python queue/client | GitHub API handling with mocked HTTP responses |
| Server container | image build, required tools, env validation |
| Compose runtime | config validation, health check, volume persistence |
| Prompt attach | canned prompt through `opencode run --attach` |
| Workspace manager | clone, reuse, fetch/reset, failure paths |
| Workflow YAML | actionlint plus full-SHA pin checks |

### Coverage Reports

For Python/client work:

- generate terminal coverage output
- generate XML/LCOV coverage data for CI
- generate an HTML coverage report artifact
- publish coverage results in the workflow summary where practical

Suggested artifact paths:

```text
test-results/
coverage.xml
coverage.lcov
htmlcov/
```

### CI Workflow Requirements

Document or add CI coverage for:

- build
- lint
- scan
- tests
- coverage
- coverage HTML artifact upload
- Docker server image build
- Docker client image build
- devcontainer prebuild while still applicable
- image publish to GHCR on `main` or release branches

Required CI artifacts:

- test results
- coverage XML or LCOV
- HTML coverage report
- Docker build logs
- image digest output
- opencode server logs for integration tests

Workflow requirements:

- every `uses:` line must be pinned to a full 40-character SHA
- every pinned action must include a release/version comment
- image publish workflows must output immutable image digests
- coverage and build artifacts must be retained long enough for review.

### Image Publishing

Server and client images should publish to GHCR only after build, lint, scan,
test, and coverage gates pass.

Minimum expected outputs:

- server image tag
- client image tag
- server image digest
- client image digest
- build provenance or summary where available

Prebuild/devcontainer publishing remains applicable only while the devcontainer
compatibility path requires it.

## Phase Gate Protocol

Every phase gate requires:

1. All task acceptance criteria checked.
2. All phase validation commands pass.
3. `pwsh -NoProfile -File ./scripts/validate.ps1 -All` passes.
4. CI is green when workflow changes are pushed.
5. Coverage report is generated for Python/client changes.
6. Docker/Compose validation passes for runtime changes.
7. No unresolved critical/high security findings remain.
8. Known environmental failures are documented with command output and reason.

The orchestrator must stop at the phase gate if validation fails. Fix validation
before beginning the next phase.

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missing Dockerfiles block all container work | Critical | Start with Phase 0 image tasks before server behavior work. |
| Path drift between `/workspaces/*` and `/opt/orchestration/*` | High | Add `ORCHESTRATION_ROOT` support and test both paths. |
| Remote attach fails silently | High | Add explicit health check and stderr/log capture before prompt dispatch. |
| Workspace concurrency corrupts repos | High | Start with serialized persistent clone reuse; add worktrees only when needed. |
| Workspace cleanup deletes useful state | Medium | Make cleanup explicit and non-default until policy is proven. |
| Credentials leak in logs or comments | Critical | Scrub GitHub-posted output and avoid logging bridge/auth secrets. |
| VS Code tunnel expands runtime scope | Medium | Keep disabled by default; defer if it needs supervision/auth complexity. |
| GitHub Actions bridge exposes server | High | Choose a minimal authenticated bridge; never log bridge secrets. |
| CI/image publishing drift | High | Pin actions by SHA and make image build/publish part of gated CI. |
| Coverage/reporting gaps hide regressions | Medium | Require coverage output and HTML artifact for Python/client changes. |

## Recommended Execution Order

```text
Phase 0: Foundation and image contract
  -> Phase 1: Standalone opencode server
  -> Phase 2: Compose runtime
  -> Phase 3: Script compatibility
  -> Phase 4: Repository workspace manager
  -> Phase 5: GitHub Actions bridge
  -> Phase 6: Operator observation
  -> Phase 7: Phase-two hardening
```

Parallelization guidance:

- Phase 0 Dockerfile work and client code fixes can run in parallel if write
  scopes are separated.
- Phase 1 server tests can run in parallel after entrypoint wiring is complete.
- Phase 2 Compose volume/env/health work should be integrated by one owner to
  avoid config conflicts.
- Phase 3 script changes should have one owner for `devcontainer-opencode.sh`
  and one owner for prompt assembly only if edits do not overlap.
- Phase 4 workspace manager work should be serialized until the repo path policy
  is stable.
- CI and validation work is part of each phase, not a final cleanup pass.

Do not begin a later phase until the prior phase gate is satisfied.

## Configuration Reference

| Variable | Phase | Purpose |
|----------|-------|---------|
| `ORCHESTRATION_ROOT` | 0 | Server filesystem root, default `/opt/orchestration`. |
| `GH_ORCHESTRATION_AGENT_TOKEN` | 0 | GitHub API, `gh`, opencode, and agents. |
| `ZHIPU_API_KEY` | 0 | Primary model provider. |
| `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY` | 0 | Secondary model provider. |
| `OPENAI_API_KEY` | 0 | Optional model provider. |
| `GEMINI_API_KEY` | 0 | Optional model provider. |
| `OPENCODE_SERVER_HOSTNAME` | 1 | Server bind hostname, default `0.0.0.0`. |
| `OPENCODE_SERVER_PORT` | 1 | Server port, default `4096`. |
| `OPENCODE_SERVER_URL` | 3 | Client/bridge attach URL. |
| `OPENCODE_SERVER_DIR` | 3 | Server-side prompt working directory. |
| `ORCHESTRATION_WORKSPACE_ROOT` | 4 | Target repo workspace root, default `/opt/orchestration/workspaces`. |
| `MCP_MEMORY_STORAGE_BACKEND` | 2 | Memory backend, expected `sqlite_vec`. |
| `MCP_MEMORY_SQLITE_PATH` | 2 | Persistent memory DB path. |
| `MCP_MEMORY_SQLITE_PRAGMAS` | 2 | SQLite tuning. |
| `WEBHOOK_SECRET` | Deferred | Future FastAPI/GitHub App webhook verification. |
| `SENTINEL_BOT_LOGIN` | Deferred | Future sentinel claim identity. |
