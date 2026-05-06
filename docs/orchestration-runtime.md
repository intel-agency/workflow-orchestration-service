# Orchestration Runtime

This is the canonical active document for the orchestration runtime, its current
state, and the migration to a standalone service. Historical runtime plans live
under `docs/.archived/` and should be treated as reference material, not active
architecture.

## Status And Scope

The current system is a GitHub Actions-driven orchestration stack that starts
`opencode serve` inside a devcontainer, assembles a prompt from a GitHub event,
and attaches an `opencode run` client to the server.

The target system is a repo-owned, Docker Compose-managed runtime that can run
as a stable local or trusted-LAN service. GitHub Actions remains the trigger and
prompt assembly layer for now, but the long-term runtime should not require
starting the opencode server inside every workflow run.

In scope for the current migration:

- standalone `opencode serve` runtime hosted by Docker Compose
- repo-owned image build and runtime contract
- persistent memory, logs, and target-repo workspaces
- current prompt/script compatibility
- GitHub Actions to local/LAN server bridge design
- optional low-complexity operator observation

Out of scope for the current migration:

- Kubernetes
- on-prem model inference
- Notion, Jira, or generic tracker migration
- GitHub App webhook replacement for GitHub Actions
- redesigning dynamic workflows or workflow assignments
- phase-one TLS, auth, and firewall hardening beyond the bridge minimum

Trusted local/LAN operation is an intentional phase-one simplification. Security
hardening remains important, but it should follow a solid runtime contract and
hosting model.

## Migration Status

Completed or partially completed:

| Area | Status |
|------|--------|
| Opencode server bootstrap | `scripts/start-opencode-server.sh` starts and reuses `opencode serve`, writes logs, and waits for readiness. |
| Container entrypoint | `scripts/entrypoint.sh` exists for image-style startup and starts the opencode server. |
| Current attach flow | `scripts/devcontainer-opencode.sh prompt` and `run_opencode_prompt.sh` support `-p`, `-f`, `-u`, and `-d`. |
| Devcontainer runtime | `.devcontainer/devcontainer.json` starts the current server through `postStartCommand`. |
| Compose scaffold | `docker-compose.yml` exists with server/client service intent and memory volume wiring. |
| Client scaffold | `client/src/` contains notifier, sentinel, queue, and work-item model scaffolding. |
| Docs decision work | Historical docs captured the move toward a self-hosted runtime and the decision to keep GitHub-centric workflow state for now. |

Incomplete:

| Area | Remaining work |
|------|----------------|
| Root server image | `docker-compose.yml` references a root `Dockerfile`, but one is not currently tracked. |
| Client image | `docker-compose.yml` references `client/Dockerfile`, but one is not currently tracked. |
| Runnable Compose path | Compose needs complete Dockerfiles, env-file contract, volumes, logs, health checks, and startup validation. |
| Workspace manager | The standalone server needs a clear clone/reuse/worktree policy for target repositories. |
| GitHub Actions bridge | The workflow-to-local/LAN server interface is not yet chosen. |
| Auth/TLS hardening | Server-side auth, TLS, and firewall guidance are phase-two work after the service contract is solid. |
| VS Code tunnel | Operator observation is only viable in phase one if it stays low-complexity. |

## Agreed Decisions

- The orchestration image is owned and built in this repository. The external
  prebuild repo is not the target architecture.
- Docker Compose is the primary standalone runtime target.
- The devcontainer path remains as a compatibility and developer convenience
  path, not the primary hosting model.
- Current scripts and prompt flows stay supported:
  - `scripts/devcontainer-opencode.sh prompt`
  - `run_opencode_prompt.sh`
  - prompt input through `-p` or `-f`
  - attach URL through `-u`
  - server-side working directory through `-d`
- GitHub Actions remains the event trigger and prompt assembly layer for now.
- Running the server inside every GitHub Actions workflow run is not the target
  destination.
- GitHub Issues, labels, comments, projects, and milestones remain the workflow
  state/control plane for this migration.
- Dynamic workflows and workflow assignments stay as they are.
- Phase one targets local or trusted-LAN operation. TLS, auth, and firewall
  hardening are phase two.
- A VS Code Insiders tunnel may be used only as an optional observation path
  into the same runtime context as opencode. It must not become the prompt
  transport.

## Open Questions

- How should GitHub Actions reach a local or LAN-hosted server?
  - Tailscale, ngrok, and a small authenticated bridge are candidate options.
  - This should remain undecided until the local Compose runtime is solid.
- What is the target repository workspace policy?
  - clone per repo
  - persistent clone reuse
  - git worktrees
  - clean per-run checkouts
- Should VS Code Insiders tunnel support remain in phase one?
  - Keep it only if it is a small optional sibling daemon.
  - If it adds meaningful process supervision, auth, image, or workspace
    complexity, move it to phase two.
- How thin should the current devcontainer wrapper become once Compose is the
  normal runtime?
- What minimal authentication is needed for the one cross-network interface from
  GitHub Actions to the local/LAN server?

## Architecture Overview

### Current Runtime

```text
GitHub event or workflow_dispatch
  -> .github/workflows/orchestrator-agent.yml
  -> actions/checkout
  -> devcontainer up
  -> .devcontainer/devcontainer.json postStartCommand
  -> scripts/start-opencode-server.sh
  -> opencode serve :4096 inside devcontainer
  -> scripts/devcontainer-opencode.sh prompt
  -> run_opencode_prompt.sh
  -> opencode run --attach http://127.0.0.1:4096
  -> orchestrator agent and specialist agents
```

### Target Runtime

```text
Local/LAN host
  -> docker compose up -d
  -> orchestration-server container
       -> opencode serve :4096
       -> persistent memory volume
       -> persistent log volume
       -> persistent workspace volume
       -> optional VS Code tunnel daemon

GitHub Actions
  -> assemble prompt / select match case
  -> call chosen bridge to local/LAN server
  -> server-side prompt execution against target repo workspace
```

### Prompt Flow

```text
caller
  -> scripts/devcontainer-opencode.sh prompt -p|-f ... -u <server-url> -d <server-dir>
  -> run_opencode_prompt.sh
  -> opencode run --attach <server-url> --agent orchestrator
  -> opencode serve
  -> orchestrator prompt handling
```

The command surface should remain familiar even after the runtime changes. The
implementation can change under the scripts, but callers should still be able to
send inline prompts, prompt files, attach URLs, and explicit server-side
directories.

### Workspace And Clone Flow

```text
event or prompt identifies target repo
  -> workspace manager resolves repo slug and ref
  -> /opt/orchestration/workspaces/<owner>/<repo>
       -> clone, fetch, reuse, worktree, or clean checkout
  -> prompt runner sets -d / OPENCODE_SERVER_DIR to that path
  -> opencode works inside the same filesystem visible to operators
```

The workspace manager is not implemented yet. The important migration decision
is that target repos must exist inside the standalone runtime, not only inside a
GitHub Actions runner checkout.

## Target Runtime Contract

Initial target contract:

| Contract item | Target |
|---------------|--------|
| Image ownership | Built and published from this repository |
| Runtime manager | Docker Compose |
| Primary service | `orchestration-server` |
| Opencode port | `4096` |
| Entrypoint | `scripts/entrypoint.sh` or image-baked equivalent |
| Server bootstrap | `scripts/start-opencode-server.sh` |
| Environment source | `.env` or Compose `env_file` |
| Memory path | `/opt/orchestration/.memory/memory.db` |
| Log path | `/opt/orchestration/logs/` or equivalent persistent volume |
| Workspace root | `/opt/orchestration/workspaces` |
| Health check | HTTP check against `http://127.0.0.1:4096/` |
| Restart policy | Compose-managed restart policy |

Expected environment variables:

| Variable | Purpose |
|----------|---------|
| `GH_ORCHESTRATION_AGENT_TOKEN` | GitHub API, `gh`, opencode, and agents |
| `ZHIPU_API_KEY` | Primary model provider |
| `KIMI_CODE_ORCHESTRATOR_AGENT_API_KEY` | Secondary model provider |
| `OPENAI_API_KEY` | Optional model provider |
| `GEMINI_API_KEY` | Optional model provider, mapped as needed |
| `OPENCODE_SERVER_HOSTNAME` | Server bind hostname, default `0.0.0.0` |
| `OPENCODE_SERVER_PORT` | Server port, default `4096` |
| `ORCHESTRATION_WORKSPACE_ROOT` | Target repo workspace root, default `/opt/orchestration/workspaces` |
| `MCP_MEMORY_STORAGE_BACKEND` | Memory backend, expected `sqlite_vec` |
| `MCP_MEMORY_SQLITE_PATH` | Persistent memory DB path |
| `MCP_MEMORY_SQLITE_PRAGMAS` | SQLite tuning |

## Repository Workspace Strategy

Historical notes identify the desired standalone strategy: the long-running
server receives a prompt or event for a target repository, then clones that
repository into the server runtime and runs the orchestration from there.

Current implementation is simpler:

- devcontainer clients assume the current repo is already mounted at
  `/workspaces/<repo-name>`
- `scripts/devcontainer-opencode.sh` passes a server-side working directory with
  `-d`
- `run_opencode_prompt.sh` attaches to the server and executes from that
  directory

Target default:

```text
ORCHESTRATION_WORKSPACE_ROOT=/opt/orchestration/workspaces
```

Target behavior:

- resolve the target repo from the event or prompt
- ensure a local checkout exists under the workspace root
- set `OPENCODE_SERVER_DIR` or `-d` to that checkout path
- keep the checkout visible to operator tooling

Still undecided:

- whether each run should use a fresh checkout, a persistent clone, or git
  worktrees
- cleanup policy for old repos and branches
- how to isolate concurrent work on the same target repo
- how to map GitHub event refs to branch/worktree checkout names

## Operator Observation

The goal is to observe and, when needed, intervene in the source repositories
that the opencode server is actively working on.

VS Code Insiders tunnel is viable only if it is low-complexity:

- it runs as a sibling daemon in the same container as `opencode serve`
- it uses the same user, workspace root, and filesystem as opencode
- it exposes the workspace root for editor, terminal, and agent observation
- it does not replace the prompt transport
- it does not require a major supervision or auth subsystem in phase one

If tunnel support meaningfully expands the runtime structure, image surface,
credentials, process supervision, or deployment complexity, defer it to phase
two.

Simpler observation paths can remain acceptable in phase one:

- `docker compose exec orchestration-server bash`
- `docker compose logs -f`
- direct filesystem access to bind-mounted workspace/log volumes

## Historical References

Archived docs are historical evidence, not active plans. The retained decisions
from them are consolidated in this document.

Key references:

- `plan_docs-self-contained/IMPLEMENTATION-PLAN.md` is the best-format source
  for the next detailed phased development plan. Its task tables, gates,
  validation commands, dependency graphs, risk register, and recommended
  execution order are worth reusing, but its scope must be reconciled with the
  agreed decisions in this document.
- `plan_docs-self-contained/Standalone Service Migration Plan -
  workflow-orchestration-service.md` contains the earlier full six-phase
  client/server migration plan, including server image work, client/sentinel
  work, webhook handling, GitHub App integration, and hardening.
- `plan_docs-self-contained/Application Implementation Specification -
  workflow-orchestration-service v1.2.md` is a condensed implementation spec
  derived from the standalone service migration plan.
- `.archived/runtime-migration/server-system-service-plan.md` captured the
  Compose-managed service direction, script compatibility requirement, and
  separation of local/LAN runtime from GitHub Actions reachability.
- `.archived/runtime-migration/onprem-gap-analysis.md` captured the narrowed
  scope: trusted local/LAN first, GitHub-centric workflow state retained, and
  doc drift as a migration risk.
- `.archived/future/new_features.md` contains early exploration of a standalone
  long-running server that clones target repos into its own runtime. It also
  contains superseded prebuild-repo ideas; those are not active decisions.
- `.archived/runtime-migration/orchestration-clients.md` documented the current
  prompt clients and the `-p` / `-f` / `-u` / `-d` surface that must remain
  compatible.

## Migration Plan

1. Documentation cleanup
   - keep this file as the canonical runtime source
   - keep older runtime docs archived
   - remove active-doc drift

2. Service contract
   - finalize image name, service name, ports, env file, volumes, health checks,
     logs, restart policy, and workspace root

3. Docker and Compose completion
   - add the missing Dockerfiles
   - make `docker compose up -d` start a working `orchestration-server`
   - persist memory, logs, and workspaces

4. Script compatibility
   - preserve current prompt behavior and flags
   - refactor wrappers toward the Compose service where practical
   - keep direct/devcontainer paths for debugging and compatibility

5. Repository workspace manager
   - implement target repo clone/fetch/worktree behavior
   - wire prompt execution directory to the chosen checkout
   - document cleanup and concurrency policy

6. GitHub Actions bridge
   - keep GitHub Actions as the listener and prompt assembler
   - choose the local/LAN bridge mechanism after the service works locally
   - avoid assuming GitHub-hosted runners can reach a private LAN service

7. Phase-two hardening
   - enforce auth on the exposed interface
   - define TLS/reverse-proxy/firewall guidance
   - add VS Code tunnel support if it was deferred

## Validation And Acceptance

After non-trivial implementation changes, run:

```powershell
pwsh -NoProfile -File ./scripts/validate.ps1 -All
```

Docs refactor checks:

```bash
find docs -maxdepth 1 -type f -name '*.md' -print | sort
grep -RInE "external prebuild repo is the t[a]rget|devcontainer.*primary h[o]sting|GitHub App webhook m[i]gration is current scope|TLS.*phase[- ]?one blocker|auth.*phase[- ]?one blocker" docs/*.md
```

Acceptance criteria:

- `docs/orchestration-runtime.md` is the only active runtime/migration narrative
  in `docs/`
- archived runtime docs are under `docs/.archived/runtime-migration/`
- speculative future docs are under `docs/.archived/future/`
- active docs do not describe the external prebuild repo as the target
  architecture
- active docs do not describe devcontainer hosting as the primary target
- active docs keep the current script and prompting surface intact
- open questions and agreed decisions are explicit
