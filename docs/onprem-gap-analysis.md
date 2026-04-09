# Self-Hosted Runtime Gap Analysis

> Note: this file keeps its historical name for continuity, but "on-prem" is
> no longer the target framing. The active goal is a self-hosted or LAN-hosted
> orchestration runtime that can still use the current cloud model providers.

## Purpose

This document captures the current gaps, misses, and architectural differences
that matter for the active target:

- run the orchestration server as a self-hosted service on a local machine or
  trusted LAN
- keep GitHub-centric triggers and workflow state for now
- keep the current model providers
- preserve the existing dynamic workflows and workflow assignments
- reduce startup friction and documentation drift

This is an assessment of the repository as it exists today, plus the specific
decisions that now narrow the migration scope.

## Scope Decisions

These are now treated as decisions, not open architecture problems.

### In scope

- a long-running self-hosted orchestration server
- Docker and Docker Compose as the service runtime direction
- keeping the current devcontainer CLI workflow as a compatibility layer
- GitHub Actions remaining the event listener
- GitHub Issues, labels, comments, projects, and milestones remaining the
  control plane
- image ownership and image build staying in this repository

### Out of scope for the current plan

- on-prem model inference
- Kubernetes
- Notion or Jira migration
- GitHub App webhook migration
- redesigning dynamic workflows or workflow assignments

## Executive Summary

The current system is best described as:

- a GitHub Actions driven orchestrator
- using GitHub Issues and labels as the state machine
- running `opencode serve` inside a devcontainer
- using external model providers, which is acceptable for the current target

The most important practical conclusion is:

- the current devcontainer-based flow already works for manual local use
- the main problem is not correctness of the orchestration logic
- the main problem is that the runtime is too manual, too editor/devcontainer
  centric, and too awkward to operate as a stable local or LAN service

Short version:

| Area | Readiness | Notes |
|------|-----------|-------|
| Current local CLI flow | Medium-High | `devcontainer-opencode.sh up/start/prompt` works and is worth preserving |
| GitHub-centric trigger model | High enough | Adequate for current needs; not a priority to replace |
| LAN-hosted server runtime | Low-Medium | Missing service packaging, auth enforcement, TLS guidance, and canonical deployment path |
| Repo-owned image and runtime contract | Low | Docs and implementation intent are currently split |
| Tracker portability | Deliberately de-prioritized | Jira and Notion are not current goals |
| Full on-prem platform | Out of scope | Not required for the current phase |

## Current Implemented Architecture

### What is actually implemented

1. Event listener
   - `.github/workflows/orchestrator-agent.yml`
   - Triggered by `issues: labeled` and `workflow_dispatch`

2. Prompt assembly
   - `scripts/assemble-orchestrator-prompt.sh`
   - `.github/workflows/prompts/orchestrator-agent-prompt.md`

3. Runtime
   - devcontainer-based `opencode serve`
   - server bootstrapper in `scripts/start-opencode-server.sh`
   - attach runner in `run_opencode_prompt.sh`

4. Local clients
   - `scripts/devcontainer-opencode.sh`
   - `scripts/prompt-direct.sh`
   - `scripts/prompt-local.ps1`
   - `scripts/assemble-local-prompt.sh`

5. Control plane
   - GitHub Issues
   - GitHub labels in `.github/.labels.json`
   - GitHub comments
   - GitHub Projects and milestones through `gh` CLI scripts

6. Workflow logic source
   - local command wrappers in `.opencode/commands/`
   - remote canonical dynamic workflows and workflow assignments in
     `nam20485/agent-instructions`

### What is working well enough

- the current server can be started locally and prompted successfully through
  `scripts/devcontainer-opencode.sh`
- the GitHub-centric event and state model is coherent for current use
- dynamic workflows and workflow assignments already provide the orchestration
  abstraction layer the system needs right now

### What the system is not today

- not a polished system service
- not a hardened LAN service
- not a Compose-managed runtime
- not documented from a single authoritative deployment model
- not in need of immediate tracker abstraction work

## Current Gaps

### 1. The runtime is functional, but too manual

This is the main active gap.

Current pain points:

- startup depends on host state across Docker, devcontainer CLI, env export,
  and GHCR/image assumptions
- the primary service lifecycle is expressed through devcontainer conventions
  rather than a normal service contract
- local and LAN operation require more manual steps than they should
- current docs describe multiple overlapping ways to run the system without one
  canonical service-hosting model

Assessment:

- this is a packaging and operability problem, not a fundamental orchestration
  problem

### 2. LAN service hardening is incomplete

Main gaps:

- `scripts/start-opencode-server.sh` binds to `0.0.0.0` but does not enforce
  auth
- `.devcontainer/devcontainer.json` passes
  `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD`, but the
  bootstrapper does not use them
- attach clients can embed basic auth, but the server does not actually require
  it
- no TLS strategy is implemented
- no reverse proxy or firewall guidance exists
- no canonical always-on service deployment exists

Assessment:

- acceptable for trusted local development
- not ready as a shared LAN service

### 3. Documentation and instruction drift is real

There are meaningful differences between the documented narrative and the files
present in the repo.

Examples:

- `AGENTS.md` says there are no `publish-docker` or `prebuild-devcontainer`
  workflows in this repo, but those workflow files are present
- `docs/local-lan-orchestration-plan.md` still lists several gaps that are now
  resolved:
  - `.env.example`
  - `scripts/setup-local-env.sh`
  - `scripts/assemble-local-prompt.sh`
  - `status` in `scripts/devcontainer-opencode.sh`
  - `docs/local-orchestration-quickstart.md`
- older docs assume the external prebuild repo is the only valid image/build
  source, while the active direction is to keep image ownership and build in
  this repo

Assessment:

- drift is now a direct migration risk because it obscures which runtime model
  is current and which one is only historical

### 4. Image ownership and build responsibility are unclear

There is a difference between:

- the currently documented story in some files
- the now-approved direction

Current drift:

- several docs still describe the external prebuild repository as the long-term
  image source
- the approved direction is to keep image ownership and image build in this
  repository

Assessment:

- this needs to be resolved in docs first, then in the migration plan, so the
  runtime has a clear source of truth

### 5. The devcontainer interface should remain, but it should stop being the primary hosting model

The current local workflow has proven useful:

```bash
bash scripts/devcontainer-opencode.sh up
bash scripts/devcontainer-opencode.sh start
bash scripts/devcontainer-opencode.sh prompt -p "..."
```

That should be preserved.

What should change:

- the canonical server runtime should become a normal containerized service
- the devcontainer interface should become a thin compatibility and developer
  convenience wrapper around that service contract

Assessment:

- preserve the UX
- change the hosting model

### 6. GitHub-centric control remains the right current tradeoff

This is not a gap to fix now.

Accepted current choices:

- GitHub Actions remains the listener
- GitHub Issues and labels remain the control plane
- dynamic workflows and workflow assignments remain as-is
- model providers remain external

This means the current migration should not be expanded into:

- Jira/Notion abstraction work
- GitHub App webhook migration
- on-prem model hosting

Assessment:

- this is deliberate scope control, not technical debt

### 7. Remote dependencies are mixed: some are acceptable, some are active
problems

Acceptable for now:

- cloud model providers
- GitHub Actions triggers
- GitHub Issues and labels
- remote `agent-instructions` repository

Active problems:

- no canonical Compose service deployment
- unclear image ownership/build story
- service docs still anchored too heavily to devcontainer hosting

## GitHub-Centric Trigger And State Assessment

### Current verdict

GitHub-centric workflow state is adequate for now.

The current issue/plan/event trigger system is tightly GitHub-specific, but that
is acceptable because tracker portability is no longer a priority.

What matters now:

- keep the trigger model stable
- keep the state machine stable
- improve the runtime underneath it

### What stays unchanged in the current plan

- `.github/workflows/orchestrator-agent.yml` remains the listener
- `issues: labeled` and `workflow_dispatch` remain the primary triggers
- labels remain the state transition mechanism
- issue comments remain the human-facing status sink
- dynamic workflows remain the execution abstraction

### What is not part of the current plan

- GitHub App event webhooks
- generic tracker adapters
- replacing labels with a new workflow state backend

## Current State Vs Target State

| Topic | Current state | Target state |
|------|---------------|--------------|
| Listener | GitHub Actions workflow | unchanged for now |
| Trigger payload | GitHub event JSON | unchanged for now |
| Workflow state | GitHub Issues, labels, comments | unchanged for now |
| Server runtime | devcontainer-hosted server | Compose-managed self-hosted service |
| Local CLI | devcontainer-first | compatibility wrapper over service runtime |
| Image ownership | mixed narrative, partially externalized story | owned and built in this repo |
| Model providers | cloud-hosted | unchanged |
| Tracker portability | previously analyzed as a big concern | explicitly de-prioritized |
| Deployment target | developer machine or runner-local runtime | stable local or LAN service |

## Recommendations

### Priority 1: Resolve drift

Do first:

- align architecture docs around the self-hosted runtime goal
- mark older planning docs as historical where needed
- stop describing the external prebuild repo as the intended long-term runtime
  source
- make it explicit that GitHub Actions remains the listener

### Priority 2: Define a canonical service runtime

Do next:

- make Docker Compose the primary service deployment path
- define the service contract for:
  - image
  - env file
  - volumes
  - memory persistence
  - ports
  - logs
  - health checks
  - restart policy

### Priority 3: Preserve and refactor the current CLI path

Then:

- keep `scripts/devcontainer-opencode.sh`
- keep current prompt flows
- refactor them into a thin wrapper over the service runtime where practical

### Priority 4: Harden LAN deployment

After the service contract exists:

- enforce auth
- define TLS strategy
- define trusted LAN deployment guidance

## Bottom Line

The active problem is not that the system is too GitHub-centric.

The active problem is that a working orchestration runtime is currently packaged
like a development environment instead of a normal service.

The right next move is:

1. clarify the docs
2. define a repo-owned Compose service runtime
3. preserve the current devcontainer CLI as a compatibility layer
4. keep GitHub-centric triggers and workflow state unchanged while that runtime
   migration happens
