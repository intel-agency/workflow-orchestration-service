# Server System Service Migration Plan

## Purpose

Move the orchestration server from a devcontainer-centric hosting model to a
normal self-hosted service model.

The target is a stable local or LAN-hosted runtime managed by Docker Compose,
while preserving the current command-line workflow and keeping GitHub Actions as
the event listener.

## Non-Goals

This plan does not include:

- Kubernetes
- on-prem model hosting
- Notion or Jira integration
- GitHub App webhook migration
- redesigning dynamic workflows or workflow assignments

## Fixed Decisions

These decisions are assumed throughout the plan.

### Trigger and state model

- GitHub Actions remains the primary listener
- `issues: labeled` and `workflow_dispatch` remain the primary triggers
- GitHub Issues, labels, comments, projects, and milestones remain the control
  plane

### Workflow logic

- dynamic workflows stay as they are
- workflow assignments stay as they are
- no migration of orchestration semantics away from GitHub is required in this
  plan

### Runtime and image ownership

- the orchestration image is owned and built in this repository
- the external prebuild repo is not the target architecture for this migration
- Docker Compose is the target runtime manager

### Provider dependencies

- the current model providers remain in use
- cloud-hosted inference is acceptable

## Problem Statement

The current runtime works, but it is too difficult to operate as a stable local
or LAN service.

Current pain points:

- startup relies on devcontainer behavior rather than a normal service contract
- the host setup is more manual than it should be
- service lifecycle is not explicit
- auth and TLS are not productionized for LAN use
- multiple docs describe overlapping runtime stories
- image ownership and deployment assumptions drift across docs

At the same time, the current local CLI flow has proven useful and should not be
discarded:

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/devcontainer-opencode.sh start
bash scripts/devcontainer-opencode.sh prompt -p "..."
```

## Target Architecture

### Canonical runtime

The canonical runtime becomes a Compose-managed service hosted on a local
machine or trusted LAN host.

Conceptually:

```text
repo-owned image
-> docker compose up
-> long-running orchestration server container
-> persistent memory/log volumes
-> prompt clients attach to the running service
```

### Primary service characteristics

The service should have:

- a stable container name and service name
- a stable port
- an env-file based configuration model
- persistent storage for memory and logs
- a health check
- a restart policy
- a clear auth story

### Compatibility path

The current devcontainer interface remains supported, but its long-term role
changes:

- developer convenience
- local parity and debugging
- compatibility wrapper over the service runtime where practical

The goal is to preserve user-facing workflows while removing devcontainer as the
primary hosting abstraction.

## Target Runtime Model

### Compose-managed service

The future primary commands should look conceptually like:

```bash
docker compose up -d
docker compose ps
docker compose logs -f
docker compose down
```

### Persistent state

At minimum, persist:

- memory database
- server log directory
- any auth or configuration files needed by the runtime

### Environment model

The service should load configuration through a canonical env path, for example:

- `.env`
- `.env.local`
- Compose `env_file`

The goal is to remove the need for repeated manual shell exporting in normal
operation.

## GitHub Actions Relationship

### What stays the same

GitHub Actions remains the event listener and prompt assembler.

That means:

- `.github/workflows/orchestrator-agent.yml` remains central
- prompt assembly remains GitHub-event aware
- dispatch issues and label-driven workflows remain unchanged

### What changes later

The execution target can evolve from:

- runner-local devcontainer runtime

to:

- a long-running service runtime

without changing the trigger model.

### Important connectivity constraint

If GitHub-hosted runners are used, they cannot be assumed to reach a private LAN
service directly.

That means the plan should separate:

1. local or LAN service migration
2. GitHub Actions integration with that service

The initial migration does not need to solve remote reachability for
GitHub-hosted runners.

## Migration Phases

### Phase 0: Documentation And Instruction Drift Cleanup

Goal:

- make the runtime story unambiguous before moving the implementation

Tasks:

- align architecture docs around the self-hosted service goal
- mark older planning docs as historical or superseded
- remove stale claims that the external prebuild repo is the intended long-term
  runtime source
- document that GitHub Actions remains the listener

Acceptance criteria:

- one current gap-analysis document
- one current migration-plan document
- service docs point to the same target architecture

### Phase 1: Define The Service Contract

Goal:

- define exactly what the self-hosted service is before changing wrappers

Tasks:

- define image name and image ownership
- define service name
- define container port mapping
- define required env vars
- define volume layout
- define health endpoint and readiness checks
- define logging location
- define auth requirements

Acceptance criteria:

- the docs specify one canonical service contract
- local users can understand the intended runtime without reading script source

### Phase 2: Restore Repo-Owned Image Build As The Source Of Truth

Goal:

- make this repository the authoritative source for the server image

Tasks:

- document image build ownership in this repo
- align workflow and docs terminology with that decision
- remove architectural dependency on the external prebuild repo from the target
  plan

Acceptance criteria:

- architecture docs consistently identify this repo as the image owner
- the migration plan does not depend on the external prebuild repo

### Phase 3: Add Docker Compose Runtime

Goal:

- make the service runnable as a normal containerized system service

Tasks:

- add a Compose stack for the orchestration server
- wire env-file loading
- wire persistent memory and logs
- add health checks
- add status and log inspection guidance

Acceptance criteria:

- one-command service startup
- one-command service shutdown
- persistent memory/log state survives container restart

### Phase 4: Refactor The Existing CLI To Sit On Top Of The Service

Goal:

- preserve the current user workflow while reducing implementation coupling to
  devcontainer bootstrapping

Tasks:

- determine which current commands stay user-facing
- keep `scripts/devcontainer-opencode.sh` available
- refactor it toward a thin wrapper over the Compose-managed service where
  practical
- keep direct prompt execution available for debugging and parity work

Acceptance criteria:

- current CLI users do not lose core workflows
- service lifecycle no longer depends on devcontainer bootstrapping for normal
  use

### Phase 5: Harden The Service For LAN Use

Goal:

- make the service acceptable on a trusted shared LAN

Tasks:

- enforce auth on the server side
- define TLS strategy
- document reverse proxy or direct-exposure guidance
- document trusted-LAN assumptions explicitly

Acceptance criteria:

- auth is enforced by the server, not only by clients
- LAN deployment guidance is explicit
- the service is no longer "open by accident"

### Phase 6: Decide How GitHub Actions Uses The Service

Goal:

- choose whether GitHub Actions continues to run a local runtime or targets the
  long-running service

Options:

1. Keep runner-local runtime in GitHub Actions
   - simplest
   - no private LAN connectivity problem

2. Use self-hosted runners on the same LAN as the service
   - allows Actions-triggered runs to target the service directly

3. Add a later remote-execution integration path
   - only if needed after the local service migration succeeds

Acceptance criteria:

- GitHub Actions execution target is explicitly documented
- no hidden assumption that GitHub-hosted runners can reach a private LAN
  service

## Acceptance Criteria For The Overall Migration

The migration is successful when:

- the orchestration server has a canonical Compose-managed deployment path
- image ownership and build responsibility are clearly owned by this repo
- the current CLI workflow still works
- normal local startup no longer requires manual devcontainer-first workflows
- server auth is actually enforced
- the documentation no longer describes competing runtime stories

## Risks And Open Questions

### 1. GitHub Actions to LAN service reachability

If the service lives on a private LAN and GitHub-hosted runners remain in use,
the workflow cannot assume direct connectivity.

Implication:

- local/LAN service migration and GitHub Actions execution-target migration must
  be treated as separate steps

### 2. How thin can the compatibility wrapper really be

The wrapper should preserve user workflows, but it should not reimplement a
second runtime manager inside shell scripts.

Implication:

- define the service contract first
- only then refactor `scripts/devcontainer-opencode.sh`

### 3. Auth and TLS details

Auth and TLS are clearly needed for a LAN service, but the exact implementation
must fit the actual capabilities of `opencode serve` and the surrounding
deployment model.

Implication:

- keep this as a hardening phase after the Compose runtime exists

## Recommended Execution Order

1. Fix documentation drift.
2. Finalize the service contract.
3. Reassert repo-owned image build as the target architecture.
4. Add the Compose runtime.
5. Refactor the current CLI around that runtime.
6. Harden the LAN deployment.
7. Make an explicit GitHub Actions execution-target decision.

## Bottom Line

The system does not need a new trigger model.

It needs a better hosting model.

The migration should therefore focus on:

- Compose-managed service runtime
- repo-owned image build
- preserved CLI compatibility
- GitHub-centric workflow continuity
