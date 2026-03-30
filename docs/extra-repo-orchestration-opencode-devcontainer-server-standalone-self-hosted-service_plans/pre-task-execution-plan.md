# Pre-Task Execution Plan

> **Source:** `docs/.../pre-task-steps.md`
> **Branch:** `feature/standalone-orchestration-service-migration`
> **Date:** 2026-03-29

This plan covers the three pre-task steps that must be completed **before** beginning the OS-APOW standalone service migration.

---

## Pre-Task 1: Rename References — `queue-tango48` → `workflow-orchestration-service`

### Background

The repo was renamed from `workflow-orchestration-queue-tango48` to `workflow-orchestration-service`. The GitHub repo and VS Code workspace file have already been renamed. All remaining in-file references need to be updated.

### Inventory of Remaining References

**37 total references** across 19 files. Grouped by intent:

#### A. Active Configuration (MUST update — affects runtime behavior)

| # | File | Count | Action |
|---|------|-------|--------|
| 1 | `AGENTS.md` | 4 | Update template repo name references to `workflow-orchestration-service`; update `template_design_constraints` placeholder names; update `gh repo create --template` example |
| 2 | `workflow-orchestration-service.code-workspace` | 1 | Update `powershell.cwd` setting from `workflow-orchestration-queue-tango48` → `workflow-orchestration-service` |
| 3 | `workflow-orchestration-queue-tango48.code-workspace` | 1 | **Delete this file** — it's the old-name workspace file, superseded by `workflow-orchestration-service.code-workspace` |

#### B. Skills & Docs (SHOULD update — examples, references)

| # | File | Count | Action |
|---|------|-------|--------|
| 4 | `.agents/skills/forensic-analysis-report/SKILL.md` | 1 | Update example prompt repo name |
| 5 | `.agents/skills/orchestration-run-analysis/SKILL.md` | 1 | Update "generated from" reference |
| 6 | `docs/local-orchestration-quickstart.md` | 2 | Update `git clone` URL and `cd` directory |

#### C. Plan Docs (SHOULD update — these describe this repo)

| # | File | Count | Action |
|---|------|-------|--------|
| 7 | `plan_docs/OS-APOW Architecture Guide v3.2.md` | 3 | Update repo name references in architecture description |
| 8 | `plan_docs/OS-APOW Development Plan v4.2.md` | 3 | Update repo name in user stories and lifecycle stages |
| 9 | `plan_docs/OS-APOW Implementation Specification v1.2.md` | 1 | Update Phase 0 cloning reference |
| 10 | `plan_docs/interactive-report.html` | 1 | Update "Manual cloning of" reference |

#### D. Migration/Feature Plan Docs (OPTIONAL — historical context)

These are planning documents that describe the original state. Changes are cosmetic.

| # | File | Count | Action |
|---|------|-------|--------|
| 11 | `docs/.../F1-feature-full-dev-plan.md` | 2 | Update or add editor note |
| 12 | `docs/.../F1-full-dev-plan_(OPENCODE).md` | 5 | Update or add editor note |
| 13 | `docs/.../OS-APOW-standalone-service-migration-plan.md` | 1 | Update env var example |
| 14 | `docs/.../new_features.md` | 1 | Update placeholder replacement reference |

#### E. Archived Docs (SKIP — historical records)

These files are in `docs/.archived/` and document past events using the old name. Updating them rewrites history.

| # | File | Count | Action |
|---|------|-------|--------|
| 15 | `docs/.archived/implementation-plan.md` | 1 | **Skip** — historical |
| 16 | `docs/.archived/non-idle-failure-forensics.md` | 3 | **Skip** — references specific run IDs |
| 17 | `docs/.archived/pr-approval-merge-plan.md` | 2 | **Skip** — historical |
| 18 | `docs/.archived/prompt-refactor-analysis.md` | 3 | **Skip** — historical |
| 19 | `docs/.archived/zulu48-fix-plan.md` | 1 | **Skip** — historical |

### Execution Steps

1. **Delete** `workflow-orchestration-queue-tango48.code-workspace`
2. **Find-and-replace** `workflow-orchestration-queue-tango48` → `workflow-orchestration-service` in files from groups A, B, C (items 1–10)
3. **Contextual updates** for group D (items 11–14) — add `[renamed]` editor notes or update inline
4. **Leave group E untouched** (archived docs)
5. **Verify** no remaining references in active files: `git grep "queue-tango48" -- ':!docs/.archived/'`
6. **Run validation**: `./scripts/validate.ps1 -All`

---

## Pre-Task 2: Manual Application of `project-setup` Dynamic Workflow

### Background

The `project-setup` dynamic workflow orchestrates initial repository setup through a sequence of assignments. This workflow was never executed for this repo. Instead of running it now, we need to:
1. Analyze what each assignment would have done
2. Determine what's already been done vs. what's still needed
3. Manually apply the remaining actions

### Project-Setup Workflow: Assignment Sequence

The **original** `project-setup` workflow runs these assignments in order:

| # | Assignment | Purpose |
|---|-----------|---------|
| 1 | `init-existing-repository` | Initialize repo structure, create setup branch/PR |
| 2 | `create-app-plan` | Create comprehensive application plan issue |
| 3 | `create-project-structure` | Set up directory structure and boilerplate |
| 4 | `create-agents-md-file` | Create/update AGENTS.md with project-specific details |
| 5 | `debrief-and-document` | Create debriefing report with 12-section template |
| 6 | `pr-approval-and-merge` | Approve and merge the setup PR |

**Pre-script event:** `create-workflow-plan` — creates a workflow execution plan issue.

**Post-assignment events** (after each assignment):
- `validate-assignment-completion` — verify outputs exist and checks pass
- `report-progress` — update progress on tracking issue

**Post-script event:** Apply `orchestration:plan-approved` label to the app plan issue.

### Analysis Required — Sub-Steps

Audit completed 2026-03-29. Each assignment's acceptance criteria were checked against the live repo state.

#### Assignment 1: `init-existing-repository`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| Create new branch | `dynamic-workflow-project-setup` branch | Feature branch exists (`feature/standalone-orchestration-service-migration`) | **DONE** (different name, but serves same purpose) |
| Import branch protection ruleset | `protected-branches` ruleset active | Ruleset exists and is `active` | **DONE** |
| Create GitHub Project | Project board for issue tracking | Project #31 `workflow-orchestration-queue-tango48` exists | **PARTIALLY DONE** — needs rename to `workflow-orchestration-service` |
| Link project to repo | Project linked to this repo | Needs verification | **NEEDS CHECK** |
| Create project columns | Not Started, In Progress, In Review, Done | Needs verification | **NEEDS CHECK** |
| Import labels | Labels from `.github/.labels.json` | 31 labels defined, 31 labels in repo — counts match | **DONE** |
| Rename workspace/devcontainer files | Repo-name prefix on files | Workspace file: `workflow-orchestration-service.code-workspace` ✅; Devcontainer name: `workflow-orchestration-prebuild-devcontainer` (uses prebuild prefix by design) | **DONE** |
| Create PR | PR from setup branch to main | PR #2 exists from feature branch | **DONE** (different name, same purpose) |

**Actions needed:**
- [ ] Rename project #31 from `workflow-orchestration-queue-tango48` → `workflow-orchestration-service`
- [ ] Verify project is linked to this repo and has correct columns

#### Assignment 2: `create-app-plan`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| Analyze app template | Understand requirements from `plan_docs/` | Plan docs exist with detailed specs | **DONE** (context exists) |
| Create plan issue | Application plan issue using template | No plan issue exists (only issue #1: dispatch trigger) | **NOT DONE** |
| Create `tech-stack.md` | `plan_docs/tech-stack.md` | Does not exist | **NOT DONE** |
| Create `architecture.md` | `plan_docs/architecture.md` | Does not exist | **NOT DONE** |
| Create milestones | Milestones from plan phases | No milestones exist | **NOT DONE** |
| Link issue to project | Plan issue linked to project board | N/A (no plan issue yet) | **NOT DONE** |

**Actions needed:**
- [ ] Create application plan issue from `plan_docs/` using `.github/ISSUE_TEMPLATE/application-plan.md` template
- [ ] Create `plan_docs/tech-stack.md` documenting Python, FastAPI, Docker, GitHub Actions, opencode
- [ ] Create `plan_docs/architecture.md` documenting OS-APOW architecture
- [ ] Create milestones for each phase (Phase 0–3 from the plan docs)
- [ ] Link plan issue to project board and assign to Phase 0 milestone

#### Assignment 3: `create-project-structure`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| Solution/project structure | Directories and project files | `client/src/`, `scripts/`, `test/`, `docs/`, `.github/workflows/` all exist | **DONE** |
| Configuration files | Docker, version pinning, etc. | `docker-compose.yml`, `global.json`, `requirements.txt`, `pyproject.toml` exist | **DONE** |
| CI/CD pipeline | GitHub Actions workflows | `orchestrator-agent.yml`, `validate.yml` exist | **DONE** |
| Documentation structure | README, docs folder | `docs/` exists with multiple docs | **DONE** |
| Repository summary | `.ai-repository-summary.md` | Does not exist | **NOT DONE** |

**Actions needed:**
- [ ] Create `.ai-repository-summary.md` at repo root

#### Assignment 4: `create-agents-md-file`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| AGENTS.md exists at root | Comprehensive agent instructions | `AGENTS.md` exists with detailed content | **DONE** |
| Project overview section | Description of purpose and tech stack | Present (describes orchestration system) | **DONE** |
| Setup/build/test commands | Verified commands | Present (`testing` section with validation commands) | **DONE** |
| Code style section | Conventions and guidelines | Present (`coding_conventions` section) | **DONE** |
| Project structure section | Directory layout | Present (`repository_map` section) | **DONE** |
| Project-specific content | Adapted from template to this repo | Template references updated (Pre-Task 1) | **DONE** |

**Actions needed:** None — AGENTS.md is comprehensive and has been updated.

#### Assignment 5: `debrief-and-document`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| Debriefing report | 12-section template document | Does not exist | **NOT APPLICABLE** — debriefing is for post-workflow execution; since we're manually applying steps, the pre-task plan itself serves this purpose |

**Actions needed:** None — skip (the pre-task execution plan serves as documentation).

#### Assignment 6: `pr-approval-and-merge`

| Step | Expected Output | Current State | Status |
|------|----------------|---------------|--------|
| PR approval | Setup PR approved and merged | PR #2 is open for the migration work | **NOT APPLICABLE** — PR #2 will be merged when migration is complete, not as a setup step |

**Actions needed:** None — PR #2 lifecycle is managed by the migration work.

#### Workflow Events

| Event | Expected Output | Current State | Status |
|-------|----------------|---------------|--------|
| `create-workflow-plan` (pre-script) | Workflow execution plan issue | Not created | **SKIP** — manual execution doesn't need a tracking issue |
| `validate-assignment-completion` (post-assignment) | Validation after each step | Will run `validate.ps1 -All` after all changes | **ADAPTED** |
| `report-progress` (post-assignment) | Progress updates on tracking issue | Tracking via this plan document | **ADAPTED** |
| `orchestration:plan-approved` label (post-script) | Label on plan issue | Will apply after plan issue is created | **PENDING** |

### Summary of Required Actions

| # | Action | Assignment | Priority | Status |
|---|--------|-----------|----------|--------|
| 1 | Rename project #31 → `workflow-orchestration-service` | init-existing-repository | Medium | ✅ Done |
| 2 | Verify project linked to repo with correct columns | init-existing-repository | Medium | ✅ Done |
| 3 | Create application plan issue | create-app-plan | High | ✅ Done (#3) |
| 4 | Create `plan_docs/tech-stack.md` | create-app-plan | Medium | ✅ Done |
| 5 | Create `plan_docs/architecture.md` | create-app-plan | Medium | ✅ Done |
| 6 | Create milestones (Phase 0–3) | create-app-plan | Medium | ✅ Done |
| 7 | Link plan issue to project, assign milestone | create-app-plan | Medium | ✅ Done |
| 8 | Create `.ai-repository-summary.md` | create-project-structure | Low | ✅ Done |
| 9 | Apply `orchestration:plan-approved` label to plan issue | post-script event | Low | ✅ Done |

---

## Pre-Task 3: Apply Upstream Template Changes

### Background

This repo was created from the template `intel-agency/ai-new-workflow-app-template`. Changes made to that template repo **after** this repo was cloned need to be identified and selectively applied. Any changes that still reference the template's own name or placeholders must be adapted to reflect this repo (`intel-agency/workflow-orchestration-service`).

### Key Facts

- **Clone date:** 2026-03-28 06:12:32 UTC-7 (commit `c7f49c3` "Initial commit")
- **Seed date:** 2026-03-28 06:12:37 UTC-7 (commit `cf001f7` "Seed ... from template with plan docs and placeholder replacements")
- **Template repo:** `intel-agency/ai-new-workflow-app-template` (canonical upstream)
- **Clone-point commit:** `540842fe` (2026-03-28T05:42:56Z — "Merge branch 'main'...")

### Upstream Commits Since Clone (6 commits)

| # | SHA | Date (UTC) | Message | Files | Action |
|---|-----|-----------|---------|-------|--------|
| 1 | `7558a690` | 2026-03-28 16:57 | docs: add subagent activity line prefix plan and trace output filtering analysis | +`docs/subagent-prefix-plan.md`, +`docs/trace-filtering-analysis-foxtrot86.md` | **APPLIED** — files copied |
| 2 | `c6981df1` | 2026-03-28 17:23 | docs: expand subagent prefix plan with implementation remarks | ~`docs/subagent-prefix-plan.md` (+60 -23) | **APPLIED** — latest version fetched |
| 3 | `bd4763fd` | 2026-03-28 19:23 | docs: clarify terminology by introducing "maestro" for orchestrator supervisor | ~`docs/orchestrator-supervisor.md` (+2) | **APPLIED** — maestro note added |
| 4 | `41e1cc76` | 2026-03-28 19:23 | docs: implement subagent prefixes for CI log clarity and FIFO cleanup | ~`docs/subagent-prefix-plan.md`, ~`run_opencode_prompt.sh` (+32 -8) | **APPLIED** — FIFO output tailer, expanded noise filter, debug-mode watchdog, cleanup |
| 5 | `9eb4b030` | 2026-03-28 19:23 | docs: add implementation approval protocol to coding conventions | ~`AGENTS.md` (+1) | **APPLIED** — approval protocol rule added to `coding_conventions` |
| 6 | `b89b6712` | 2026-03-29 06:47 | docs: update agent configurations to deprecate tools in favor of permission | ~18 agent `.md` files | **ALREADY APPLIED** — done in earlier commit `86ee06a` |

### Adaptation Notes

- No template-specific references (`ai-new-workflow-app-template`) were present in the upstream change content — all changes were generic and applied directly.
- The `run_opencode_prompt.sh` changes were applied after verifying the local file structure matched the upstream pre-change state (FIFO already existed for server log but not for client output log).

### Expected Output

All 6 upstream commits have been applied. No further action needed for Pre-Task 3.

---

## Execution Status

| Pre-Task | Status | Date |
|----------|--------|------|
| **1. Rename References** | **COMPLETE** — 25 references updated across 14 files; old workspace file deleted; 10 archived refs intentionally preserved | 2026-03-29 |
| **2. Project Setup Audit** | **COMPLETE** — all 9 actions executed | 2026-03-29 |
| **3. Upstream Changes** | **COMPLETE** — 6 commits applied (5 new + 1 already done) | 2026-03-29 |

### Pre-Task 2 Execution Results

All 9 actions from the project-setup audit have been completed:

| # | Action | Result |
|---|--------|--------|
| 1 | Rename project #31 | **DONE** — renamed to `workflow-orchestration-service` via GraphQL |
| 2 | Verify project linked to repo with correct columns | **DONE** — Status field has Not Started, In Progress, In Review, Done |
| 3 | Create application plan issue | **DONE** — Issue #3 created with full OS-APOW implementation plan |
| 4 | Create `plan_docs/tech-stack.md` | **DONE** — documents Python, FastAPI, opencode, Docker, etc. |
| 5 | Create `plan_docs/architecture.md` | **DONE** — system overview, 4 pillars, data flow, security model |
| 6 | Create milestones (Phase 0–3) | **DONE** — 4 milestones created (Phase 0 through Phase 3) |
| 7 | Link plan issue to project, assign milestone | **DONE** — Issue #3 linked to project #31, assigned to Phase 0 milestone |
| 8 | Create `.ai-repository-summary.md` | **DONE** — repo summary at root |
| 9 | Apply `orchestration:plan-approved` label to plan issue | **DONE** — label applied to Issue #3 |
