# Subagent & Server Trace Output — Implementation Report

> **Purpose**: Document the methods, problems, failed approaches, and lessons learned from achieving full trace visibility into (1) server agent output and (2) delegated subagent output during headless CI execution of the OpenCode CLI orchestrator. This report is intended to accelerate a re-implementation in a similar project.
>
> **Sources**: `docs/.archived/opencode-subagent-tracing/`, `docs/.archived/subagent-prefix-plan.md`, `run_opencode_prompt.sh`, `opencode.json`, `scripts/trace-extract.py`, `scripts/WorkItemModel.py`, and associated implementation plans and forensic reports.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Server Agent Trace Output](#2-server-agent-trace-output)
3. [Delegated Subagent Trace Output](#3-delegated-subagent-trace-output)
4. [Problems Encountered](#4-problems-encountered)
5. [Approaches That Did Not Work](#5-approaches-that-did-not-work)
6. [Key Learnings for Re-Implementation](#6-key-learnings-for-re-implementation)
7. [Recommended Implementation Order](#7-recommended-implementation-order)
8. [Reference: Configuration Artifacts](#8-reference-configuration-artifacts)

---

## 1. Architecture Overview

The system runs in a **client-server topology** inside a GitHub Actions devcontainer:

```
opencode serve  ──►  headless server process (DEBUG logging, --print-logs)
                        │
                        ├─ Writes rotating logs to ~/.local/share/opencode/log/*.log
                        ├─ Writes server log to /tmp/opencode-serve.log
                        └─ Manages subagent child sessions (isolated, no parent stdout)

opencode run    ──►  client process (attaches to server, runs orchestrator prompt)
                        │
                        ├─ Writes client output to /tmp/opencode-output.XXXXXX
                        └─ Blocks silently during subagent delegation (no stdout)
```

**The core observability problem**: OpenCode's subagent architecture deliberately isolates child sessions from parent stdout. The parent client blocks opaquely during subagent execution — producing no output at all. The server process is busy (LLM API calls, tool execution, database writes), but its stdout/stderr goes to its own log file, not the client's stream. This creates a **silent gap** in CI output that can last many minutes, making it impossible to distinguish "working" from "hung."

---

## 2. Server Agent Trace Output

### 2.1 Method That Worked

The successful approach combined three techniques:

#### A. Server Started with DEBUG Logging + `--print-logs`

```bash
# In scripts/start-opencode-server.sh:
opencode serve --log-level DEBUG --print-logs > /tmp/opencode-serve.log 2>&1 &
```

- **Why**: The server at INFO level misses subagent session details entirely. DEBUG level captures `Task` tool dispatches, `childSessionId` creation, full tool execution traces, and LLM request/response payloads.
- `--print-logs` forces the daemon to emit structured log entries to stderr (captured in the log file).

#### B. Live Server Log Tailer Streaming to CI stdout

A dedicated function `_stream_server_subagent_log()` in `run_opencode_prompt.sh` tails the server log file, filters out noise, and pipes to CI stdout with a `[server]` prefix:

```bash
tail -f -n +$START_LINE "$SERVER_LOG" \
  | grep -Ev "$_SERVER_LOG_NOISE" \
  | grep -v '^\s*$' \
  | sed -u 's/^/[server] /' &
```

- **FIFO pattern**: Uses a named pipe (`mkfifo`) to separate the `tail -f` PID from the filter pipeline. This allows explicit kill of `tail -f` during cleanup, preventing orphaned processes that hold the devcontainer cgroup open.
- **Noise filtering**: A comprehensive `_SERVER_LOG_NOISE` regex (~20 patterns) suppresses per-token noise, tool registry init, permission blobs, LSP file touches, file timings, snapshot hashes, formatter checks, and more. This removed **~510 lines** of noise per run.
- **Blank line filtering**: `grep -v '^\s*$'` removed another **~170 lines** of blank `[server]` output.

#### C. Artifact Upload on Every Run

```yaml
# In .github/workflows/orchestrator-agent.yml:
- name: Upload Debug Logs
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: opencode-traces
    path: |
      ~/.local/share/opencode/log/*.log
      /tmp/opencode-serve.log
      subagent-traces.txt
  retention-days: 14
```

- Changed from `if: failure()` to `if: always()` so traces are available even for successful runs (useful for cost analysis and subagent behavior auditing).

### 2.2 Noise Patterns Filtered (Server Log)

The following patterns were identified and suppressed from server log streaming:

| Pattern | Reason |
|---|---|
| `service=bus` | One line per LLM token delta (`message.part.delta`/`updated`) — hundreds per run |
| `service=tool.registry` | Tool init/teardown chatter on every session loop |
| `service=permission` | Permission ruleset evaluation (very verbose JSON blobs) |
| `service=bash-tool` | Bash shell initialization line |
| `service=provider` | Provider init/found lines at startup (~9 lines per run) |
| `service=lsp` | LSP "touching file" on every file read |
| `service=file.time` | File read timing per file access |
| `service=snapshot` | Snapshot hash lines emitted every LLM step |
| `cwd=.*tracking` | Follow-on cwd line paired with `service=snapshot` |
| `service=session.processor` | Process tick emitted every LLM step |
| `service=session.compaction` | Pruning log on compaction |
| `service=session.prompt status=` | `resolveTools` started/completed per step |
| `service=format` | Formatter availability check (~27 lines per file write) |
| `service=vcs` | Branch change tracking line per checkout |
| `service=storage` | Storage migration lines at startup |
| `ruleset=[{"permission"` | Terminal line of multi-line bash permission pre-check blob |
| `action={"permission"` | Terminal line of multi-line bash permission post-check blob |
| `mcp stderr: .*running on` | MCP server startup "running on stdio" line |
| `service=llm .*stream$` | LLM stream start per session step |
| `session.prompt step=.*loop$` | Session prompt loop iteration |
| `mcp stderr:\s*$` | Blank mcp stderr flush lines |

### 2.3 Problems Encountered (Server Traces)

| Problem | Root Cause | Resolution |
|---|---|---|
| Server logs at INFO missed subagent session details | INFO level does not emit `Task` tool dispatches or child session IDs | Server now runs at DEBUG level |
| Server log dump required `DEBUG_ORCHESTRATOR=true` | Was gated behind debug flag | Changed to `if: always()` — visible in every CI run |
| Orphaned `tail -f` holding devcontainer cgroup open | Killing only the filter pipeline end (sed) leaves `tail -f` orphaned with no EOF signal | FIFO pattern: track `tail -f` PID separately, kill it explicitly |
| Server log flooding CI output with noise | DEBUG level produces hundreds of lines per token, per tool call | Comprehensive `_SERVER_LOG_NOISE` regex filtering |
| Blank `[server]` lines in output | Filtered lines left empty lines that still got the `[server]` prefix | Added `grep -v '^\s*$'` after noise filter |

---

## 3. Delegated Subagent Trace Output

### 3.1 Method That Worked

The successful approach was a **multi-layered strategy** combining real-time CI output streaming, post-mortem artifact extraction, and watchdog heartbeat enhancement.

#### Layer 1: Client Output Prefixing (Real-Time CI Visibility)

Subagent delegation markers (`•` start, `✓` complete) and tool operations (`→` file read, `%` web fetch, `⚙` MCP tool call) are emitted by the OpenCode CLI to client stdout but had no prefix, blending with other output.

**Solution**: Insert a `sed` filter between `tail -f` and CI stdout:

```bash
tail -f "$OUTPUT_LOG" > "$_output_pipe" &
OUTPUT_TAIL_RAW_PID=$!
sed -u -e '/[•✓]/s/^/[subagent] /' -e '/[→%⚙]/s/^/[agent] /' < "$_output_pipe" &
TAIL_PID=$!
```

**Result in CI output**:
```
[subagent] • Execute project-setup workflow General Agent
[agent] → Read .opencode/commands/orchestrate-dynamic-workflow.md
[agent] ⚙ memory_read_graph Unknown
Thinking: Now I have the full project-setup workflow...
[subagent] ✓ Execute project-setup workflow General Agent
```

- **Option chosen**: `[subagent]` for `•`/`✓` (delegation lifecycle), `[agent]` for `→`/`%`/`⚙` (tool operations). This splits task delegations from tool calls for easy grepping.
- **FIFO pattern**: Same named-pipe approach as the server tailer to prevent orphaned `tail -f` processes.

#### Layer 2: Post-Mortem Trace Extraction (Full Forensic Detail)

OpenCode writes rotating JSON logs to `~/.local/share/opencode/log/*.log` (max 10 files, ISO 8601 timestamped). These contain the complete subagent trace including `childSessionId`.

**Extraction pipeline**:
1. `scripts/trace-extract.py` parses the rotating JSON logs
2. Extracts subagent sessions by `childSessionId`
3. Applies `scrub_secrets()` from `WorkItemModel.py` to prevent credential leaks
4. Outputs chronological per-subagent trace dumps to `subagent-traces.txt`
5. Uploaded as a GitHub Actions artifact with 14-day retention

**Sentinel-to-Subagent correlation**:
```bash
# Get the ID of the most recent subagent dispatched
SUB_ID=$(grep "tool=Task" ~/.local/share/opencode/log/*.log | jq -r '.childSessionId' | tail -n 1)
# Dump the full reasoning of that specific subagent
grep "$SUB_ID" ~/.local/share/opencode/log/*.log | jq -r '.message' > subagent_trace.txt
```

#### Layer 3: Watchdog Heartbeat Enhancement (Liveness During Silent Delegations)

The most critical problem: during subagent execution, the client produces **zero stdout**. The watchdog loop detects this by reading the server process's cumulative I/O counters from `/proc/<pid>/io`.

**Split read/write tracking**:
- `write_bytes` changing → strong signal of genuine progress (DB writes, file output, tool results). Resets idle timer fully.
- `read_bytes` changing (but writes flat) → weaker signal. Grants a shorter `READ_ONLY_GRACE` period.
- Neither changing → truly idle.

**Watchdog output during subagent execution**:
```
[watchdog] client output idle 82s, server write I/O active (write_bytes=125829120) — subagent likely running
```

In `DEBUG_ORCHESTRATOR=true` mode, the watchdog also echoes the last 3 lines of recent server activity:
```
[watchdog] recent server activity:
  | {"level":"DEBUG","msg":"tool_call","tool":"readFile",...}
  | {"level":"DEBUG","msg":"tool_result","tool":"readFile",...}
  | {"level":"DEBUG","msg":"tool_call","tool":"writeFile",...}
```

### 3.2 Problems Encountered (Subagent Traces)

| Problem | Root Cause | Resolution |
|---|---|---|
| No visibility during subagent execution (silent for minutes) | Client blocks opaquely during `Task` tool delegation; no stdout from client or server | Watchdog with `/proc/<pid>/io` read/write tracking provides liveness heartbeat |
| Subagent activity lines had no prefix in CI log | OpenCode CLI emits Unicode symbols without any bracketed prefix | `sed` filter adds `[subagent]` / `[agent]` prefix |
| `tail -f` orphaned processes hanging workflow jobs | Killing pipeline end (sed) leaves `tail -f` orphaned; regular file has no EOF signal | FIFO pattern: named pipe + separate PID tracking for `tail -f` |
| `trace-extract.py` had no credential scrubbing | Raw log output contained API keys, tokens, and secrets | Imported `scrub_secrets()` from `WorkItemModel.py`; scrubbing on by default |
| `OPENCODE_VERBOSE=true` caused massive log bloat | Dumps full HTTP bodies including large prompt payloads | Used only in targeted debug runs, not always-on |
| Log rotation losing early subagent traces | OpenCode retains only 10 log files; long runs lose early traces | Artifact upload at checkpoints; `trace-extract.py` runs as post-step with `if: always()` |
| `client.app.log()` plugin traces don't appear on stdout | Known bug in OpenCode ~v1.0.220 — plugin logs write to files but not `--print-logs` terminal | Always check log files, not just terminal output |

---

## 4. Problems Encountered (Cross-Cutting)

### 4.1 Orphaned Process / Hung Workflow

**The single most destructive issue** in the entire implementation.

When the script killed the filter pipeline end (e.g., `kill $TAIL_PID` which is the `sed` process), the `tail -f` process was left orphaned. Since the output log is a regular file (not a socket), `tail -f` has no natural EOF signal after the opencode process exits. The orphaned `tail -f` holds the devcontainer exec session cgroup open **indefinitely**, causing the GitHub Actions workflow to never finish.

**Solution applied to both client and server tailers**:
```bash
# FIFO pattern — separates 'tail -f' PID from filter pipeline PID
_output_pipe=$(mktemp -u /tmp/opencode-output-tail.XXXXXX)
mkfifo "$_output_pipe"
tail -f "$OUTPUT_LOG" > "$_output_pipe" 2>/dev/null &
OUTPUT_TAIL_RAW_PID=$!           # This MUST be killed explicitly
sed -u '...' < "$_output_pipe" &
TAIL_PID=$!
rm -f "$_output_pipe"            # Safe to remove after both ends are open

# Cleanup:
kill "$OUTPUT_TAIL_RAW_PID" 2>/dev/null; wait "$OUTPUT_TAIL_RAW_PID" 2>/dev/null
kill "$TAIL_PID" 2>/dev/null;    wait "$TAIL_PID" 2>/dev/null
```

### 4.2 Server/Client Log Level Mismatch

Initially the server ran at INFO and the client at INFO — subagent session details were invisible in both streams. The fix was to bump the server to DEBUG while keeping the client at INFO (to avoid noise in the main output). The noise filtering regex made this viable.

### 4.3 Watchdog False Positives

The original watchdog only tracked client output freshness. During subagent delegation, the client is silent but the server is busy. The watchdog would incorrectly declare the process "idle" and kill it. The fix was to add server-side I/O tracking via `/proc/<pid>/io` with **split read/write byte counters**.

### 4.4 Credential Leaks in Artifacts

Raw trace output contains API keys, PATs, bearer tokens, and provider keys. The `WorkItemModel.py` scrubber covers:
- GitHub PATs (classic, fine-grained, app, OAuth)
- Bearer tokens
- OpenAI keys
- ZhipuAI keys

This scrubber was integrated into `trace-extract.py` and runs by default before artifact upload.

### 4.5 Exit Code Masking

The script originally exited `0` after idle-killing opencode, which masked SIGTERM (exit code 143) as success in GitHub Actions. Fixed to `exit 1` on idle kill so workflows properly report failure.

---

## 5. Approaches That Did Not Work

### 5.1 Plugin-Based Tool Lifecycle Hooks (Option E)

**What was attempted**: Create a TypeScript plugin at `.opencode/plugins/tracer/index.ts` to hook `tool.execute.before` and `tool.execute.after` for intercepting every tool call.

**Why it failed**: Go source code inspection (2026-03-27) found **no** `tool.execute.before`/`tool.execute.after` hook points or plugin lifecycle API in the OpenCode/Crush codebase. The Go agent uses `fantasy.NewParallelAgentTool` internally but does not expose plugin hooks to external TypeScript code. This option was **entirely hallucinated** by an earlier LLM analysis.

**Status**: ⚠️ Treat as speculative until verified against a future release.

### 5.2 OpenTelemetry Distributed Tracing (Option F)

**What was attempted**: Enable `experimental.openTelemetry: true` in `opencode.json`, install `@opentelemetry/sdk-node`, and export OTLP spans to an observability backend.

**Why it failed**: Go source code inspection (2026-03-27) found **no** OpenTelemetry integration, `experimental.openTelemetry` config key, or `@opentelemetry/sdk-node` usage in the OpenCode/Crush codebase. The `@devtheops/opencode-plugin-otel` package was not found in any registry. This option was **entirely hallucinated**.

**Status**: ⚠️ Treat as entirely speculative.

### 5.3 Real-Time Subagent Summary Lines

**What was attempted**: Parse `trace-extract.py` output mid-session and echo a 1-line summary per subagent after each `✓` completion marker.

**Why it didn't work**: Requires `trace-extract.py` to run mid-session while the server log is still being written. The client blocks on `opencode run` during subagent execution, so there's no hook point to trigger extraction. Would require a sidecar process — too complex for the benefit.

**Status**: Deferred. Not feasible with current architecture.

### 5.4 GitHub Actions `::notice::` Annotations

**What was attempted**: Emit `::notice::` annotations for each delegation start/end, showing up as badges in the GHA summary tab.

**Why it didn't work**: Requires real-time detection of Task dispatches from the client side. The client blocks opaquely during subagent execution — no callback, hook, or streaming event is available to intercept. Would require a sidecar tailing the server log.

**Status**: Deferred. Would need a sidecar architecture.

### 5.4 `--format json` Always-On

**What was attempted**: Run `opencode run --format json` for all CI executions to get structured output.

**Why it was abandoned**: JSON output interleaved with TUI characters produces unreadable terminal output. The `--format json` flag is now only activated when `DEBUG_ORCHESTRATOR=true`. For normal runs, the prefix-based approach (`[subagent]`/`[agent]`/`[server]`) provides sufficient structured visibility in human-readable form.

### 5.5 Removing `[watchdog]` Lines Entirely

**What was attempted**: Gate all watchdog output behind `DEBUG_ORCHESTRATOR` since `[subagent]` prefixes would provide progress feedback.

**Why it didn't work**: The `[subagent]` `•`/`✓` lines only appear at delegation **start** and **end**. During the execution (which can last many minutes), the client is silent. The watchdog heartbeat is the **only** signal visible during a long silent delegation. The main watchdog line is preserved; only the redundant `recent server activity:` echo block was gated behind `DEBUG_ORCHESTRATOR`.

---

## 6. Key Learnings for Re-Implementation

### 6.1 The FIFO Pattern is Non-Negotiable

If you use `tail -f` in any script that runs inside a CI devcontainer, **always** separate the `tail -f` PID from the filter pipeline PID using a named pipe. Without this, cleanup kills will orphan `tail -f`, which holds the cgroup open and causes the workflow to hang indefinitely.

```bash
pipe=$(mktemp -u /tmp/my-pipe.XXXXXX)
mkfifo "$pipe"
tail -f "$LOG_FILE" > "$pipe" &
RAW_PID=$!
filter_command < "$pipe" &
FILTER_PID=$!
rm -f "$pipe"

# Cleanup:
kill "$RAW_PID"; wait "$RAW_PID"
kill "$FILTER_PID"; wait "$FILTER_PID"
```

### 6.2 Server DEBUG + Noise Filtering is the Only Viable Combo

Running the server at DEBUG level without noise filtering produces **hundreds of lines per token**, making CI logs unusable. Running at INFO without DEBUG loses subagent traces entirely. The combination of DEBUG + comprehensive noise regex is the only approach that provides both fidelity and readability.

**Build your noise regex incrementally**: Start with the most verbose patterns (`service=bus`, `service=tool.registry`, `service=permission`), run a workflow, identify the next noisiest pattern, add it, repeat.

### 6.3 Split Read/Write I/O Tracking is Essential

Tracking only `write_bytes` will kill subagents doing network-heavy work (PR reviews, API calls) where writes plateau. Tracking only `read_bytes` makes idle detection impossible because background socket reads increment perpetually. **Track them separately** with different grace periods.

### 6.4 Credential Scrubbing Must Be Applied Before Any Artifact Upload

Raw trace logs contain secrets. Always pipe through a scrubber before uploading as artifacts, posting to issues, or streaming to external systems. Extend the scrubber patterns whenever you add a new provider API key format.

### 6.5 Log Rotation Will Bite You on Long Runs

OpenCode retains only 10 log files. If your orchestrator runs for hours with many subagent delegations, early traces will be rotated out. Mitigate by:
- Running `trace-extract.py` as a post-step (captures what's still on disk)
- Copying logs to a persistent location at checkpoints during long runs
- Increasing rotation limits if configurable in future versions

### 6.6 The `[subagent]` / `[agent]` Prefix Split is Worth It

Initially considered a single `[opencode]` prefix for all activity lines. The split (`[subagent]` for `•`/`✓`, `[agent]` for `→`/`%`/`⚙`) proved more valuable because:
- `grep '\[subagent\]'` instantly shows delegation lifecycle
- `grep '\[agent\]'` shows tool operations
- Visual distinction between "what was delegated" and "what tools were used"

### 6.7 Two Hallucinated Options Wasted Effort

The plugin hooks (Option E) and OTEL (Option F) approaches were generated by an LLM analysis that did not verify against the actual Go source code. **Always verify feature existence against the actual codebase** before investing implementation effort. The repo's `subagent-tracing-options-report.md` now marks both as ⚠️ UNVERIFIED.

### 6.8 `client.app.log()` Has a Known Stdout Bug

In OpenCode ~v1.0.220, plugin log traces written via `client.app.log()` don't propagate to `--print-logs` terminal output. They **are** written to log files. Always check files, not just terminal output, when debugging plugin-based tracing.

### 6.9 Exit Code Handling Matters

If you kill the orchestrator process (idle timeout, hard ceiling), make sure the script exits non-zero. Exiting `0` masks failures in GitHub Actions, causing incomplete runs to appear as "succeeded."

---

## 7. Recommended Implementation Order

For a new project implementing the same tracing stack, follow this phased approach:

### Phase 1 — Post-Mortem Artifact Collection (Day 1)

| Action | Effort | Impact |
|---|---|---|
| Server starts with `--log-level DEBUG --print-logs` | 1 line change | Captures all subagent traces |
| Add artifact upload step to workflow (`if: always()`) | 5 lines YAML | Downloadable debug bundles |
| Integrate credential scrubber into trace extraction | Import + call | Prevents secret leaks |
| Run trace extraction as post-step | 3 lines YAML | Distilled per-subagent summaries |

### Phase 2 — Live Trace Streaming (Day 2-3)

| Action | Effort | Impact |
|---|---|---|
| Add `[subagent]`/`[agent]` prefix filter to client log tailer | 1 line sed | Real-time delegation visibility |
| Add server log tailer with noise filtering | ~30 lines bash | Real-time subagent activity |
| Implement FIFO pattern for both tailers | ~10 lines bash | Prevents orphaned processes |
| Build noise regex incrementally | Iterative | Keeps CI output readable |

### Phase 3 — Watchdog Enhancement (Day 3-4)

| Action | Effort | Impact |
|---|---|---|
| Add `/proc/<pid>/io` read/write split tracking | ~40 lines bash | Detects server-side progress |
| Wire into idle detection loop | Modify existing loop | Prevents false idle kills |
| Add `READ_ONLY_GRACE` period | 1 variable | Handles read-heavy subagents |

### Phase 4 — Hardening (Ongoing)

| Action | Effort | Impact |
|---|---|---|
| Gate `recent server activity:` echo behind `DEBUG_ORCHESTRATOR` | 2 lines | Reduces normal-run noise |
| Ensure exit code propagation | 1 line | Correct failure reporting |
| Extend credential scrubber patterns | As needed | Covers new providers |
| Monitor log rotation impact | Ongoing | Ensure trace completeness |

---

## 8. Reference: Configuration Artifacts

### 8.1 Key Files

| File | Purpose |
|---|---|
| `run_opencode_prompt.sh` | Main orchestrator launcher — contains client tailer, server tailer, watchdog loop, cleanup |
| `scripts/start-opencode-server.sh` | Server startup — DEBUG logging, `--print-logs` |
| `scripts/trace-extract.py` | Post-mortem subagent trace extraction with credential scrubbing |
| `scripts/WorkItemModel.py` | Pydantic models + `scrub_secrets()` function |
| `opencode.json` | OpenCode configuration — providers, models, permissions, MCP servers |
| `.github/workflows/orchestrator-agent.yml` | CI workflow — artifact upload, debug log dump |

### 8.2 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENCODE_LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG` for full traces) |
| `OPENCODE_PRINT_LOGS` | `true` | Force log emission to stderr |
| `OPENCODE_VERBOSE` | *unset* | Dump full HTTP bodies (use sparingly) |
| `OPENCODE_EXPERIMENTAL` | `1` | Enable experimental features |
| `DEBUG_ORCHESTRATOR` | `false` | Gate verbose diagnostics, `--format json`, recent activity echo |
| `OPENCODE_SERVER_LOG` | `/tmp/opencode-serve.log` | Server log file path |
| `OPENCODE_SERVER_PIDFILE` | `/tmp/opencode-serve.pid` | Server PID file for `/proc/io` monitoring |

### 8.3 Idle Detection Parameters

| Parameter | Value | Purpose |
|---|---|---|
| `IDLE_TIMEOUT_SECS` | 900 (15 min) | Kill after no I/O activity |
| `READ_ONLY_GRACE_SECS` | 1200 (20 min) | Grace period for read-only activity |
| `HARD_CEILING_SECS` | 5400 (90 min) | Absolute maximum runtime |
| Watchdog interval | 30s | Check frequency |

### 8.4 Subagent Line Symbols

| Symbol | Meaning | Prefix | Agent Name? |
|---|---|---|---|
| `•` | Task delegated (start) | `[subagent]` | Yes (at end) |
| `✓` | Task completed (done) | `[subagent]` | Yes (at end) |
| `→` | File read | `[agent]` | No |
| `%` | Web fetch | `[agent]` | No |
| `⚙` | MCP tool call | `[agent]` | No |

---

## Appendix: What Changed Per Commit

| Date | Commit | Change |
|---|---|---|
| 2026-03-21 | — | Phase 1: Server DEBUG logging, credential scrubbing, artifact collection |
| 2026-03-28 | `22f0b94` | Phase 2: `--print-logs` on server, live server log tailer, enhanced watchdog, always-dump server logs |
| 2026-03-28 | — | Subagent prefix plan: `[subagent]`/`[agent]` split in client tailer, FIFO cleanup |
| 2026-03-28 | — | Trace filtering: Phases 1-3 (noise patterns, blank lines, watchdog echo gated) |
