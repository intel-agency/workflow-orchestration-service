# Dependency Readiness Report

Generated: 2026-05-28
Repo: `intel-agency/workflow-orchestration-service`
Branch: `mn/migration-status`
Mission scope: Phase 0 (foundation/Dockerfiles), Phase 1 (server container with `opencode serve`), Phase 2 (Python sentinel client dispatching prompts to remote server).
Allocated host ports: `14096` (server), `18000` (client). Internal container ports: `4096` / `8000`.

## Tool Availability

| Tool           | Status    | Version / Notes                                                                |
|----------------|-----------|--------------------------------------------------------------------------------|
| docker         | available | 29.5.2 (build 79eb04c); daemon up; storage driver `overlayfs`; 2 stopped containers, 1 image |
| docker compose | available | v5.1.4 (Docker Compose plugin)                                                 |
| docker buildx  | available | v0.34.0                                                                        |
| pwsh           | available | PowerShell 7.6.2                                                               |
| python3        | available | Python 3.13.5 on host (mission containers will pin 3.12-slim)                  |
| uv             | available | 0.11.8 (Astral; provides `uvx`)                                                |
| node           | available | v24.15.0 (via nvm)                                                             |
| npm            | available | 11.12.1                                                                        |
| bun            | available | 1.3.13                                                                         |
| gh             | available | 2.46.0; authenticated as `nam20485` via `GITHUB_TOKEN` (scopes: project, read:org, read:packages, repo, workflow). Secondary keyring login present. |
| opencode       | available | 1.15.5 on host; running on `0.0.0.0:4096` (do not disturb)                    |
| bash           | available | GNU bash 5.2.37                                                                |

## Validation Tooling

All five tools were missing initially. The repo's `scripts/install-dev-tools.ps1` failed because it targets `/usr/local/bin` (root-only) and there is no passwordless `sudo`. They were installed manually into `~/.local/bin` (already on PATH) and `~/.nvm/.../bin` (npm global). All are now functional.

| Tool                | Status    | Notes                                                                |
|---------------------|-----------|----------------------------------------------------------------------|
| actionlint          | available | 1.7.12 (downloaded release binary to `~/.local/bin/actionlint`)      |
| shellcheck          | available | 0.10.0 (downloaded static binary to `~/.local/bin/shellcheck`)       |
| gitleaks            | available | 8.21.2 (downloaded release binary to `~/.local/bin/gitleaks`)        |
| markdownlint-cli2   | available | v0.22.1 (markdownlint v0.40.0) installed via `npm i -g`              |
| hadolint            | available | 2.12.0 (downloaded release binary to `~/.local/bin/hadolint`)        |
| jq                  | available | jq-1.7 (already present)                                             |
| PSScriptAnalyzer    | available | 1.24.0 (already present)                                             |
| Pester              | available | 5.7.1 (already present)                                              |

> NOTE: `scripts/install-dev-tools.ps1` itself reports each as `NOT FOUND` in its own session because it uses `/usr/local/bin`. The next subagent should either (a) prepend `~/.local/bin` for the validate run (it is already on PATH for the user shell), or (b) the script could be patched to honor a user-bin install dir. No patching done here.

## Python Package Install (server image deps)

- Result: **success**
- Method: `uv venv /tmp/.v_readiness --python 3.12 --seed`, then `uv pip install fastapi==0.115.0 httpx==0.27.0 pydantic==2.9.0 'uvicorn[standard]==0.30.0'`.
- `python -m pip install ...` failed because the bare `uv venv` does not seed pip; `--seed` or `uv pip install` must be used. **Mission Dockerfile takeaway:** if the server image base is `python:3.12-slim` (which has pip), use `pip install`. If the image uses `uv` to build a venv, use `uv pip install` or `uv venv --seed`.
- Final import probe printed: `ok 0.115.0 0.27.0 2.9.0 0.30.0`.
- Cleanup: temporary venv moved to `/tmp/trash/.v_readiness_done_*` (not deleted, per session policy).

## Docker Daemon Check

- `docker run --rm hello-world`: **pass** — daemon executed container and printed canonical "Hello from Docker!" message.
- `docker run --rm --pull always python:3.12-slim python -c "print('ok')"`: **pass** — image pulled fresh (`Digest: sha256:090ba77e...`) and printed `ok`. Confirms outbound registry pull works for the Phase 1/2 base image.

## opencode Model Config

- Default `model` value in `opencode.json`: **`zai-coding-plan/glm-5`**
- `glm-4.7` defined under `provider.zai-coding-plan.models`: **yes** (alongside `glm-5`, `glm-4.7-flash`, `glm-4.7-flashx`).
- Required change: **Override the default model to `zai-coding-plan/glm-4.7` for the mission's server container** (user has banned `glm-5`). This can be done via env var, a container-local `opencode.json` override, or a CLI flag (`--model zai-coding-plan/glm-4.7`). Do **not** mutate the repo-root `opencode.json` unless that is part of the mission scope, since it ships to all template clones.
- `small_model` is `google/gemini-3.1-flash-lite-preview` (fine).

## Secrets Inventory

| Variable                       | Status    | Required For                                                                              |
|--------------------------------|-----------|-------------------------------------------------------------------------------------------|
| `ZHIPU_API_KEY`                | **unset** | **BLOCKER** — required by `opencode serve` to call ZhipuAI GLM models in Phase 1 server   |
| `GH_ORCHESTRATION_AGENT_TOKEN` | set       | Sentinel client polling GitHub events / posting comments (Phase 2)                        |
| `GITHUB_TOKEN`                 | set       | `gh` CLI auth (already used by host gh login); GHCR pulls if needed                       |
| `WEBHOOK_SECRET`               | unset     | Phase 3 only (out of scope here); document for later                                      |

> Values were not echoed; only `[set]`/`[unset]` recorded.

## Port Availability

- **14096:** free
- **18000:** free
- Currently listening (notable): `0.0.0.0:4096` (existing opencode server — must not be disturbed), `0.0.0.0:7700`, `*:1716`. None of the mission's allocated host ports collide.
- No process is bound to `:14096`, `:18000`, `:5173`, `:3000`, `:8000`, or `:8080`.

## Reference Modules

| File                                                                  | Exists |
|-----------------------------------------------------------------------|--------|
| `plan_docs-self-contained/src/orchestrator_sentinel.py`               | yes    |
| `plan_docs-self-contained/src/notifier_service.py`                    | yes    |
| `plan_docs-self-contained/src/WorkItemModel.py`                       | yes    |
| `plan_docs-self-contained/src/models/__init__.py`                     | yes    |
| `plan_docs-self-contained/src/models/work_item.py`                    | yes    |
| `plan_docs-self-contained/src/queue/__init__.py`                      | yes (empty file) |
| `plan_docs-self-contained/src/queue/github_queue.py`                  | yes    |

## Blockers

1. **`ZHIPU_API_KEY` is not set in this environment.** Phase 1 (server container running `opencode serve`) cannot make actual model calls without it. The Dockerfile + container plumbing can still be built and unit-tested without it, but any end-to-end smoke test against ZhipuAI requires the key. **Resolution required from user:** export `ZHIPU_API_KEY` in the environment used to run smoke tests, or accept that Phase 1 verification stops at "container starts and `/health` responds".
2. **No passwordless `sudo`.** The repo's `scripts/install-dev-tools.ps1` writes to `/usr/local/bin` and silently fails for actionlint/shellcheck/gitleaks/hadolint here. Tools were instead installed under `~/.local/bin` (already on PATH). The next subagent running `validate.ps1` will succeed in this shell, but a fresh shell or a CI-style run that doesn't inherit `~/.local/bin` on PATH would fail. Consider invoking with `PATH="$HOME/.local/bin:$PATH"` explicitly.

## Surprises / Constraints

- **`opencode` is already running on host port `4096`.** The mission's choice of `14096` for the server's host-side port is correct; mapping to internal container port `4096` is unaffected.
- **`uv venv` does not seed pip by default in 0.11.8.** Use `--seed` or `uv pip install` directly. This affects how the Phase 1 server `Dockerfile` should be written if it builds a venv.
- **`opencode` host version is `1.15.5`**, while `AGENTS.md` documents `1.2.24`. Mission may inherit whichever the prebuilt devcontainer ships; for the new standalone server image, the team should pin a known-good `opencode` version explicitly in the Dockerfile.
- **`python3` on host is 3.13.5**, but mission Dockerfile targets `python:3.12-slim`. The version skew is fine for build/test on host as long as no 3.13-only syntax is used; the Phase 2 sentinel client should pin to 3.12 to match the container image to avoid drift.
- **Two `gh` accounts** are present in `gh auth status` (one via `GITHUB_TOKEN`, one via keyring). The active one matches what the orchestrator workflow needs; just be aware that scripts using `gh` will use the `GITHUB_TOKEN`-backed identity.
- **`docker compose` is v5.x.** Some legacy compose files use top-level `version:` which v5 silently ignores; not a blocker, just noted.
- **Validation tools install path:** the repo has no record of a user-bin fallback in `install-dev-tools.ps1`. If the mission promises clean reproducibility on fresh machines, consider patching that script (out of scope here).
- **`plan_docs-self-contained/src/queue/__init__.py` is a 0-byte file** — fine, just confirms the package marker is present but empty.
