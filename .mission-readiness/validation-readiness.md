# Validation Readiness Report

Generated: 2026-05-28 (UTC, host clock 05:38)
Branch: `mn/migration-status` (uncommitted changes left untouched)
Repo root: `/home/nam20485/src/github/intel-agency/workflow-orchestration-service`
Mission allocated host ports: **14096** (server) / **18000** (client). Internal: 4096 / 8000.

---

## validate.ps1 Results

All four invocations executed with `PATH="$HOME/.local/bin:$PATH"` so the dependency-readiness-installed
tools (actionlint, shellcheck, hadolint, gitleaks, etc.) were resolved.

| Job   | Exit | Time (`real`) | Notes                                                                                  |
|-------|------|---------------|----------------------------------------------------------------------------------------|
| -Lint | 0    | 5.082 s       | actionlint, hadolint, shellcheck, PSScriptAnalyzer, JSON syntax all PASS               |
| -Scan | 0    | 0.441 s       | gitleaks PASS                                                                          |
| -Test | 0    | 12.758 s      | Pester + prompt-assembly + image-tag-logic + watchdog-io-detection — 36 + 23 PASS      |
| -All  | 0    | 17.004 s      | Combined run; identical PASS surface; well under the 120 s mission timeout cap         |

### Failure excerpts

None. The full suite is currently green on this branch.

---

## Python Test Toolchain

- **client install: FAIL** (blocker for any future pytest-based validation surface).
- **pyproject `name` field**: `"7"` (literal string `"7"`).
- **uv pip install --system** rejected with `externally managed environment` (PEP 668) on the host
  Python 3.13 interpreter. Switching to a fresh venv (`uv venv .venv-readiness` +
  `uv pip install --python .venv-readiness/bin/python -e ".[dev]"`) reached hatchling and then
  failed with:

  ```
  ValueError: Unable to determine which files to ship inside the wheel using the following heuristics: ...
  The most likely cause of this is that there is no directory that matches the name of your project (7).
  ```

  The hatchling build backend cannot resolve packages because the project name is `"7"` and no
  `7/` directory exists; `[tool.hatch.build.targets.wheel]` is also absent.

- **collect-only output**: not reachable. `python -m pytest -x --co -q` reported
  `No module named pytest` because the install never completed.

- The temporary venv was moved out of the working tree to
  `/tmp/readiness-trash/.venv-readiness` (delete blocked by session policy; not deleted).

---

## Dockerfile Gap Confirmation

- root `Dockerfile`: **missing** (`ls Dockerfile` → `No such file or directory`).
- `client/Dockerfile`: **missing** (`ls client/Dockerfile` → `No such file or directory`).
- `docker compose config` itself **succeeded** (exit 0) — it only renders the merged spec and
  does not validate referenced Dockerfile presence. Both services declare:
  - `orchestration-server`: `build.context=<repo root>`, `dockerfile=Dockerfile`, port `4096`
  - `orchestration-client`: `build.context=<repo>/client`, `dockerfile=Dockerfile`, port `8000`
  - Network: `orchestration-net` (bridge); volume `server-memory` mounted at `/opt/orchestration/.memory`.
- Real build error from `docker compose build orchestration-server`:

  ```
  #2 [internal] load build definition from Dockerfile
  #2 transferring dockerfile: 2B done
  failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory
  ```

  Both Dockerfiles must be authored before `docker compose up` will succeed. (Note: `compose build --dry-run`
  silently reports "Built" — do not rely on it as a real build check.)

---

## opencode CLI

- **version**: `1.15.5` (from `/home/nam20485/.bun/bin/opencode`)
- **`run --attach` available**: **yes** — flag advertised as `--attach` taking a server URL
  (e.g. `http://localhost:4096`); `--dir` becomes a remote-server path when attaching.
- **`serve --port` available**: **yes** — `--port` (default `0`, random) plus `--hostname`
  (default `127.0.0.1`), `--mdns`, `--cors`. Suitable for binding internal `4096` and exposing
  via the host-side `14096` mapping.

A long-lived `opencode serve` is already running on `:4096` from a prior session and was
intentionally left alone.

---

## Resource Baseline

- **Memory**: `Mem: total 125Gi, used 15Gi, free 91Gi, buff/cache 19Gi, available 109Gi; Swap: 29Gi total, 0B used`
- **CPU load**: `05:38:06 up 4:00, 1 user, load average: 1.16, 1.29, 1.33` (20-core host → ~6 % busy)
- **Process count**: `959`
- **Containers** (all stopped): two `hello-world` exited 3 weeks ago (`cranky_sammet`, `amazing_bell`); no running containers.
- **Disk free** for repo mount (`/dev/md3` on `/home`): `1.7T total, 189G used, 1.5T avail (12%)`.

---

## Container Lifecycle Smoke Test

Test container (not mission-specific): `nginx:alpine` mapped `14096:80`.

- **nginx start**: **PASS** — image pulled, container ID `03235c8213fc…`, `docker run` exit 0.
- **curl :14096**: **PASS** — `curl -fsS http://127.0.0.1:14096/` returned the nginx welcome page (exit 0).
- **nginx stop**: **PASS** — `docker stop` exit 0; `--rm` auto-removed; `docker ps -a --filter name=readiness-nginx` empty.

Conclusion: host port 14096 binds cleanly, no interference from the resident `opencode serve` on 4096.

---

## Concurrency Recommendation

Headroom math (host: 20 cores, 109 GiB available RAM, load ~1.3):
- 70 % of 109 GiB ≈ 76 GiB usable.
- 70 % of 20 cores ≈ 14 cores usable.

| Surface             | Max Concurrent | Rationale                                                                                                                                                                                                              |
|---------------------|----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| container-lifecycle | **3**          | Each instance = build/run with both server (~1.5 GiB) and client (~400 MiB) containers + opencode subprocess. Theoretical headroom ≈ 8, but mission user chose **moderate (max 3)** which also keeps disk + GHCR pull churn predictable. |
| cli-lifecycle       | **3**          | Each instance = bash/python + curl + opencode `run --attach`; ~250 MiB per worker. Theoretical headroom ≫ 20, but capped at the mission-wide moderate ceiling of **3** for orchestration consistency.                  |

Effective system-wide cap: **3 concurrent validators across all surfaces**, per user choice.

---

## Blockers

1. **Missing Dockerfiles (mission-critical)**: both `Dockerfile` and `client/Dockerfile` are absent.
   `docker compose build` cannot succeed; the container-lifecycle validation surface is therefore
   non-functional until Phase 0/1 authors them.
2. **`client/pyproject.toml` is unbuildable**: `name = "7"` plus no matching package directory and
   no `[tool.hatch.build.targets.wheel]` causes hatchling to refuse the build, which blocks
   `pytest` (and any python-based validator) from running against the client codebase.
3. **System Python is PEP 668 externally-managed**: `uv pip install --system` is rejected; future
   automation must always use a venv (`uv venv` / `python -m venv`) before installing client deps.
4. (Not strictly a blocker, but flagged) **`docker compose build --dry-run` is misleading**: it
   reports "Built" even with no Dockerfile present. Validation tooling that asserts on build
   readiness must use a real `docker compose build` (or `docker buildx build --check`) instead.

No tooling gaps remain in `validate.ps1 -All` itself — that suite is fully wired up and green.

---

## Validation Path Summary

The host-level validation toolchain is healthy: `validate.ps1 -All` completes in ~17 s with all
ten checks passing, gitleaks/actionlint/hadolint/shellcheck/PSScriptAnalyzer/Pester are all
resolvable on PATH, the resident `opencode` CLI (1.15.5) supports both `serve --port` and
`run --attach`, and the host has ample headroom (109 GiB free RAM, 1.5 TiB disk, load ~1.3) to
sustain the user-selected moderate cap of 3 concurrent validators. The host port 14096 binds
cleanly via a smoke-tested nginx container without disturbing the existing opencode server on
:4096. **However, the container-lifecycle and Python-test surfaces of the mission cannot be
exercised end-to-end yet**: both Dockerfiles required by `docker-compose.yml` are missing, and
the client `pyproject.toml` (`name = "7"`, no matching package directory) is unbuildable. Until
Phase 0/1 lands real Dockerfiles and a corrected `pyproject.toml`, the only validators that can
run green are the programmatic `validate.ps1` suite plus the CLI surface against the existing
opencode server.
