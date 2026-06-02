# Idle Timeout Implementation Report

> **Purpose**: Document the methods, problems, failed approaches, and lessons learned from implementing a robust idle timeout watchdog for the OpenCode CLI orchestrator running in GitHub Actions. This report covers the timer mechanism, activity detection, trace output during execution, and termination handling.
>
> **Sources**: `docs/.archived/idle-timeout-forensic-report.md`, `docs/.archived/zulu48-forensic-report.md`, `docs/.archived/workflow-issues-and-fixes.md` (Issues 21-22), `docs/.archived/opencode-subagent-tracing/subagent-tracing-options-report.md`, `run_opencode_prompt.sh`, `test/test-watchdog-io-detection.sh`.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Idle Timeout Timer and Detection](#2-idle-timeout-timer-and-detection)
3. [Trace Output During Execution](#3-trace-output-during-execution)
4. [Action Execution on Timeout](#4-action-execution-on-timeout)
5. [Problems Encountered](#5-problems-encountered)
6. [Approaches That Did Not Work](#6-approaches-that-did-not-work)
7. [Key Learnings for Re-Implementation](#7-key-learnings-for-re-implementation)
8. [Recommended Implementation Order](#8-recommended-implementation-order)
9. [Reference: Configuration Parameters](#9-reference-configuration-parameters)

---

## 1. Architecture Overview

The idle timeout watchdog operates as a **background monitoring loop** within `run_opencode_prompt.sh`, running concurrently with the main `opencode run` process. It implements a **dual-channel activity detection** mechanism that monitors both client output freshness and server-side I/O activity.

### 1.1 The Core Problem

When the orchestrator delegates work to a subagent via OpenCode's `Task` tool:

1. The `opencode run` **client blocks silently** waiting for the server-side subagent to finish
2. During this blocking period, **no client stdout is produced**
3. The server process is busy (LLM API calls, tool execution, database writes) but its stdout/stderr goes to a separate log file
4. A naive watchdog measuring only client output freshness would **incorrectly declare the process idle** and kill it

This is exactly what happened in **5 consecutive orchestrator failures** across 4 deployed template clones (delta61, bravo74, kilo57, juliet62) in March 2026 — all idle timeout kills during the `review-epic-prs` / `pr-approval-and-merge` step.

### 1.2 System Topology

```
┌─────────────────────────────────────────────────────────────────┐
│ GitHub Actions Runner (devcontainer)                            │
│                                                                 │
│  ┌─────────────────────┐     ┌─────────────────────────────┐   │
│  │  opencode run       │     │  Watchdog Loop              │   │
│  │  (client process)   │     │  (while kill -0 $PID)       │   │
│  │                     │     │                             │   │
│  │  stdout → OUTPUT_LOG│     │  Every 30s:                 │   │
│  │  (no output during  │     │  1. Check client output     │   │
│  │   subagent deleg.)  │     │     mtime (OUTPUT_LOG)      │   │
│  │                     │     │  2. Check server I/O via    │   │
│  │                     │     │     /proc/<pid>/io          │   │
│  └──────────┬──────────┘     │  3. Compute effective idle  │   │
│             │                │  4. Kill if idle ≥ 15 min   │   │
│             │                └──────────────┬──────────────┘   │
│             │                               │                   │
│             ▼                               ▼                   │
│  ┌─────────────────────┐     ┌─────────────────────────────┐   │
│  │  opencode serve     │     │  /proc/<spid>/io            │   │
│  │  (server process)   │     │  read_bytes: 125829120      │   │
│  │                     │     │  write_bytes: 83886080      │   │
│  │  stderr → SERVER_LOG│     │  (cumulative counters)      │   │
│  │  (DEBUG logging)    │     │                             │   │
│  └─────────────────────┘     └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Key Design Decisions

| Decision | Rationale |
|---|---|
| **30-second polling interval** | Frequent enough to catch stalls quickly; infrequent enough to avoid overhead |
| **Split read/write I/O tracking** | `write_bytes` = strong progress signal; `read_bytes` = weaker "still alive" hint with shorter grace period |
| **15-minute idle timeout** | Allows for slow subagent operations (API waits, CI checks) while catching genuine stalls |
| **90-minute hard ceiling** | Absolute safety net for runs that are technically "active" but making no real progress |
| **SIGTERM → 10s wait → SIGKILL** | Graceful shutdown attempt followed by force-kill to prevent zombie processes |

---

## 2. Idle Timeout Timer and Detection

### 2.1 Method That Worked

The successful approach combines **three independent signals** with a **tiered grace window** system:

#### Signal 1: Client Output Freshness (File Mtime)

```bash
output_last_mod=$(stat -c %Y "$OUTPUT_LOG" 2>/dev/null || echo "$now")
output_idle=$(( now - output_last_mod ))
```

- **What it measures**: Time since the client process last wrote to stdout
- **Strengths**: Simple, reliable, directly measures user-visible activity
- **Weaknesses**: Goes silent during subagent delegation (false idle signal)

#### Signal 2: Server Write Bytes (Strong Progress Signal)

```bash
read _cur_server_read _cur_server_write <<< "$(_io_split)"

if [[ -n "$_prev_server_write" && "$_cur_server_write" != "$_prev_server_write" ]]; then
    write_active=true
    _last_write_time=$now
fi
```

- **What it measures**: Cumulative bytes written by the server process (disk I/O, SQLite commits, log emission)
- **Strengths**: Hard evidence of genuine progress; immune to background socket reads
- **Weaknesses**: Misses network-heavy work (API response ingestion without disk writes)

#### Signal 3: Server Read Bytes (Weaker "Alive" Signal)

```bash
if [[ -n "$_prev_server_read" && "$_cur_server_read" != "$_prev_server_read" ]]; then
    read_active=true
    _last_read_time=$now
fi
```

- **What it measures**: Cumulative bytes read by the server process (API responses, model token streaming)
- **Strengths**: Catches network I/O that write-only monitoring misses
- **Weaknesses**: Can be fooled by background reads (system calls, inotify, `/proc` self-reads)

#### Tiered Grace Window Logic

```bash
write_idle=$(( now - _last_write_time ))
read_idle=$(( now - _last_read_time ))

if [[ "$write_active" == true ]]; then
    # Writes happening → strong progress signal, not idle
    server_idle=0
elif [[ "$read_active" == true && $write_idle -lt $READ_ONLY_GRACE_SECS ]]; then
    # Reads happening, writes paused but within grace → still alive
    server_idle=0
elif [[ -n "$_cur_server_write" ]]; then
    # /proc/io available but no qualifying activity this interval
    server_idle=$write_idle
else
    # /proc/io not available — fall back to log mtime
    server_idle=$server_log_idle
fi

# Effective idle = minimum of client and server idle time
if [[ $output_idle -le $server_idle ]]; then
    idle=$output_idle
else
    idle=$server_idle
fi
```

**Key insight**: `read_bytes` changing without `write_bytes` changing grants a **shorter grace period** (`READ_ONLY_GRACE_SECS=1200`, 20 min) because it may indicate a polling loop or API retry rather than genuine progress.

### 2.2 The `_read_server_io_split()` Function

```bash
_read_server_io_split() {
    local pidfile="$SERVER_PIDFILE"
    if [[ -f "$pidfile" ]]; then
        local spid
        spid=$(cat "$pidfile" 2>/dev/null)
        if [[ -n "$spid" && -f "/proc/$spid/io" ]]; then
            # Output "read_bytes write_bytes" as two space-separated values
            awk '/^read_bytes:/{r=$2} /^write_bytes:/{w=$2} END{print r, w}' \
                "/proc/$spid/io" 2>/dev/null
            return
        fi
    fi
    echo ""
}
```

**Why this awk pattern**:
- Matches Linux `/proc/<pid>/io` format exactly (field names followed by colon and value)
- Returns both values even if one is zero
- Returns empty string if `/proc` is unavailable (graceful degradation)

### 2.3 Constants and Thresholds

| Constant | Value | Purpose |
|---|---|---|
| `IDLE_TIMEOUT_SECS` | 900 (15 min) | Kill after no qualifying I/O activity |
| `READ_ONLY_GRACE_SECS` | 1200 (20 min) | Grace period for read-only activity |
| `HARD_CEILING_SECS` | 5400 (90 min) | Absolute maximum runtime |
| Watchdog interval | 30s | Polling frequency |

### 2.4 Problems Encountered (Timer & Detection)

| Problem | Root Cause | Resolution |
|---|---|---|
| Premature idle kill during active subagent work | Single 30s interval where `write_bytes` didn't change caused `server_io_active` to flip false; fallback used log mtime which reflected startup time, not last activity | Track `_last_server_io_time` timestamp instead of falling back to log mtime |
| Network-heavy API work invisible to watchdog | `write_bytes` only monitoring misses API response ingestion (reads without writes) | Add `read_bytes` monitoring with separate `READ_ONLY_GRACE_SECS` window |
| Background socket reads fooling idle detection | Summing `read_bytes + write_bytes` made idle detection impossible — background reads increment perpetually | Track read/write separately; writes are strong signal, reads are weaker with grace period |
| `/proc/<pid>/io` unavailable in some environments | Container isolation, permission restrictions, or non-Linux platforms | Graceful fallback to server log file mtime (less accurate but functional) |
| Race condition in activity flag evaluation | Activity flags evaluated once per loop but used across iterations without reset | Reset `write_active`/`read_active` to `false` at start of each loop iteration |

---

## 3. Trace Output During Execution

### 3.1 Method That Worked

The watchdog produces **tiered diagnostic output** based on the `DEBUG_ORCHESTRATOR` environment variable:

#### Normal Mode (Concise Heartbeats)

```bash
elif [[ $output_idle -ge 60 && "$server_io_active" == true ]]; then
    if [[ "$write_active" == true ]]; then
        echo "[watchdog] client output idle ${output_idle}s, server write I/O active (write_bytes=${_cur_server_write}) — subagent likely running"
    else
        echo "[watchdog] client output idle ${output_idle}s, server read I/O active (read_bytes=${_cur_server_read}, write_idle=${write_idle}s/${READ_ONLY_GRACE_SECS}s grace) — subagent likely running"
    fi
```

**Example output**:
```
[watchdog] client output idle 82s, server write I/O active (write_bytes=125829120) — subagent likely running
[watchdog] client output idle 145s, server write I/O active (write_bytes=167772160) — subagent likely running
```

#### Debug Mode (Full Diagnostics)

```bash
if [[ "${DEBUG_ORCHESTRATOR:-}" == "true" ]]; then
    echo "[watchdog] elapsed=${elapsed}s output_idle=${output_idle}s server_idle=${server_idle}s write_active=${write_active} read_active=${read_active} effective_idle=${idle}s log_size=${log_size}b log_lines=${log_lines} pid=$OPENCODE_PID read_bytes=${_cur_server_read:-n/a} write_bytes=${_cur_server_write:-n/a} write_idle=${write_idle:-n/a}s read_idle=${read_idle:-n/a}s"
fi
```

**Example output**:
```
[watchdog] elapsed=886s output_idle=886s server_idle=0s write_active=true read_active=true effective_idle=0s log_size=2847193b log_lines=3847 pid=12345 read_bytes=524288000 write_bytes=146317312 write_idle=15s read_idle=8s
```

#### Recent Server Activity Echo (Debug Mode Only)

```bash
if [[ "${DEBUG_ORCHESTRATOR:-}" == "true" && -f "$SERVER_LOG" ]]; then
    _recent=$(tail -20 "$SERVER_LOG" 2>/dev/null | grep -Ev "$_SERVER_LOG_NOISE" | grep -v '^$' | tail -3)
    if [[ -n "$_recent" ]]; then
        echo "[watchdog] recent server activity:"
        echo "$_recent" | sed 's/^/  | /'
    fi
fi
```

**Example output**:
```
[watchdog] recent server activity:
  | {"level":"DEBUG","msg":"tool_call","tool":"readFile","file":"src/orchestrator.py"}
  | {"level":"DEBUG","msg":"tool_result","tool":"readFile","status":"success"}
  | {"level":"DEBUG","msg":"tool_call","tool":"writeFile","file":"tests/test_orchestrator.py"}
```

### 3.2 Pre-Termination Diagnostics

When the watchdog fires (idle kill or hard ceiling), it always dumps the server log tail:

```bash
if [[ $IDLE_KILLED -eq 1 && -f "$SERVER_LOG" ]]; then
    echo "=== server log tail (last 80 lines before idle kill) ==="
    tail -n 80 "$SERVER_LOG" 2>/dev/null || true
    echo "=== end server log tail ==="
fi
```

This is critical for post-mortem debugging — it shows what the server was doing in the minutes before the kill.

### 3.3 Problems Encountered (Trace Output)

| Problem | Root Cause | Resolution |
|---|---|---|
| Watchdog messages obscured by other output | Long `[watchdog]` lines with many fields wrapped across multiple terminal lines | Concise mode uses minimal fields; debug mode gated behind `DEBUG_ORCHESTRATOR` |
| No visibility into what subagent was doing | Watchdog said "subagent likely running" but not what work was happening | Debug mode echoes last 3 lines of filtered server activity |
| Server log dump only on `DEBUG_ORCHESTRATOR=true` | Critical forensics hidden behind debug flag | Server log tail now dumped on **every** idle kill, regardless of debug mode |
| Read-only grace period not visible in normal output | Normal mode only showed `write_bytes` | Enhanced message shows `write_idle=${write_idle}s/${READ_ONLY_GRACE_SECS}s grace` when reads are active |

---

## 4. Action Execution on Timeout

### 4.1 Method That Worked

The termination sequence implements **graceful degradation with escalation**:

```bash
if [[ $idle -ge $IDLE_TIMEOUT_SECS ]]; then
    echo ""
    echo "::error::opencode idle for $(( idle / 60 ))m (no output from client or server); terminating"
    kill "$OPENCODE_PID" 2>/dev/null
    # Escalate to SIGKILL if SIGTERM doesn't work within 10s
    sleep 10
    if kill -0 "$OPENCODE_PID" 2>/dev/null; then
        echo "::warning::opencode did not exit after SIGTERM; sending SIGKILL"
        kill -9 "$OPENCODE_PID" 2>/dev/null
    fi
    IDLE_KILLED=1
    break
fi
```

**Key behaviors**:
1. **`::error::` annotation**: GitHub Actions surfaces this prominently in the workflow summary (not buried in logs)
2. **SIGTERM first**: Allows graceful cleanup (close connections, flush buffers)
3. **10-second grace period**: Reasonable time for cleanup without wasting CI minutes
4. **SIGKILL escalation**: Prevents zombie processes and hung workflows
5. **`IDLE_KILLED=1` flag**: Triggers post-mortem log dump and non-zero exit

### 4.2 Hard Ceiling Termination

```bash
if [[ $elapsed -ge $HARD_CEILING_SECS ]]; then
    echo ""
    echo "::error::opencode hit ${HARD_CEILING_SECS}s hard ceiling; terminating"
    kill "$OPENCODE_PID" 2>/dev/null
    sleep 10
    if kill -0 "$OPENCODE_PID" 2>/dev/null; then
        echo "::warning::opencode did not exit after SIGTERM; sending SIGKILL"
        kill -9 "$OPENCODE_PID" 2>/dev/null
    fi
    IDLE_KILLED=1
    break
fi
```

**Purpose**: Catches runs that are technically "active" (small I/O every 14 minutes) but making no real progress — a safety net for edge cases the idle detection misses.

### 4.3 Exit Code Propagation

```bash
# Exit non-zero on idle kill so the workflow properly reports failure.
# Previously this was `exit 0` which masked SIGTERM (143) as success,
# causing incomplete runs to appear as "succeeded" in GitHub Actions.
if [[ $IDLE_KILLED -eq 1 ]]; then
    exit 1
fi

exit ${OPENCODE_EXIT}
```

**Critical fix**: The original implementation exited `0` after idle-killing opencode, which caused GitHub Actions to report the workflow as "succeeded" despite incomplete work. This was fixed in commit `cafd0b0` (Issue 21).

### 4.4 Cleanup of Background Tailers

```bash
# Stop the client output tailer — must kill 'tail -f' (OUTPUT_TAIL_RAW_PID) explicitly.
if [[ -n "${OUTPUT_TAIL_RAW_PID:-}" ]]; then
    kill "$OUTPUT_TAIL_RAW_PID" 2>/dev/null
    wait "$OUTPUT_TAIL_RAW_PID" 2>/dev/null
fi
kill "$TAIL_PID" 2>/dev/null
wait "$TAIL_PID" 2>/dev/null

# Stop the server log tailer — must kill 'tail -f' (SERVER_TAIL_RAW_PID) explicitly.
if [[ -n "${SERVER_TAIL_RAW_PID:-}" ]]; then
    kill "$SERVER_TAIL_RAW_PID" 2>/dev/null
    wait "$SERVER_TAIL_RAW_PID" 2>/dev/null
fi
if [[ -n "${SERVER_TAIL_PID:-}" ]]; then
    kill "$SERVER_TAIL_PID" 2>/dev/null
    wait "$SERVER_TAIL_PID" 2>/dev/null
fi

# Final safety net: kill any remaining background jobs
jobs -p | xargs -r kill 2>/dev/null || true
wait 2>/dev/null || true
```

**Why this matters**: Without explicit kill of the `tail -f` processes (separate from the filter pipeline), they become orphaned and hold the devcontainer exec session cgroup open **indefinitely**, causing the GitHub Actions workflow to hang forever even after the main process exits.

### 4.5 Problems Encountered (Termination)

| Problem | Root Cause | Resolution |
|---|---|---|
| Exit code 0 masked SIGTERM (143) as success | Script exited `0` after idle kill to suppress error noise | Changed to `exit 1` on `IDLE_KILLED=1` |
| `::warning::` annotations buried in logs | Idle kills are failures, not warnings | Changed to `::error::` annotation |
| No SIGKILL escalation after SIGTERM | Zombie processes lingered for minutes | Added 10s wait then `kill -9` |
| Orphaned `tail -f` processes hanging workflows | Killing filter pipeline (sed) left `tail -f` orphaned with no EOF signal | FIFO pattern: track `tail -f` PID separately, kill explicitly |
| Server log not dumped on idle kill without debug flag | Critical forensics hidden | Always dump server log tail on idle kill |

---

## 5. Problems Encountered (Cross-Cutting)

### 5.1 Premature Idle Kill During Active Subagent Work (Issue 22)

**Symptoms**: Orchestrator killed after 15 minutes despite server actively processing subagent work.

**Root cause**: Race condition in the watchdog loop. When checking server activity via `/proc/<pid>/io write_bytes`, a single 30-second interval where `write_bytes` didn't change caused `server_io_active` to flip to `false`. The fallback used `server_log_idle` (mtime of `/tmp/opencode-serve.log`), which only reflected server **startup** time — not last activity. So `server_idle` jumped from 0 to the full runtime (~950s), immediately triggering the 15m idle kill.

**Log evidence** (india42 — buggy behavior):
```
11:44:44 [watchdog] client output idle 886s, server I/O active (write_bytes=146317312) — subagent likely running
11:45:14 Warning: opencode idle for 15m (no output from client or server); terminating
```

**Resolution** (commit `5d89c97`): Track `_last_server_io_time` (timestamp of last observed I/O activity) instead of falling back to server log mtime. The process is only killed when server I/O has been truly inactive for a full 15 minutes since it was last observed.

### 5.2 Network-Heavy Work Invisible to Write-Only Monitoring

**Symptoms**: Subagents doing PR reviews, API calls, or HTTP fetches killed prematurely despite being actively engaged in work.

**Root cause**: `/proc/<pid>/io write_bytes` only captures disk writes (SQLite commits, file output, log emission). Network I/O (API response ingestion, model token streaming) increments `read_bytes` but not `write_bytes` when data is processed in memory without hitting disk.

**Forensic evidence** (idle-timeout-forensic-report.md):
> "The PR review subagent has server `write_bytes` activity for the first ~5 minutes in observed runs. After that, a 15-min idle window fires. The subagent is waiting on GitHub API responses or LLM streaming — network I/O that doesn't increment write_bytes."

**Resolution**: Add `read_bytes` monitoring with a separate `READ_ONLY_GRACE_SECS` window. Reads without writes grant 20 minutes (vs. 15 minutes for complete idle) because they may indicate API waits rather than stalls.

### 5.3 Exit Code Masking (Issue 21)

**Symptoms**: Workflow runs appeared as "succeeded" in GitHub Actions despite being killed by the watchdog.

**Root cause**: The wrapper script exited `0` after idle-killing opencode to suppress error noise in the workflow summary.

**Log evidence**:
```
Warning: opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143                     ← SIGTERM received
Notice: devcontainer-opencode.sh exited with code: 0   ← BUG: should be non-zero
```

**Resolution** (commit `cafd0b0`): Exit `1` when `IDLE_KILLED=1`, ensuring GitHub Actions reports the workflow as failed.

### 5.4 Permission Blocking Masquerading as Idle Timeout

**Symptoms**: Subagent dispatches `gh` bash commands, all are evaluated as `action: ask` by permission ruleset, subagent waits silently for human approval that never arrives in headless CI, watchdog fires after 15 minutes.

**Root cause**: The opencode permission ruleset contains `{"permission":"bash","pattern":"*","action":"ask"}` which routes all bash tool invocations to a human confirmation gate. In headless CI, no human is present to approve.

**Forensic evidence** (zulu48-forensic-report.md):
```
INFO  2026-03-28T01:08:35 +0ms service=permission permission=bash pattern=gh pr view 5 ...
action={"permission":"bash","pattern":"*","action":"ask"} evaluated
INFO  2026-03-28T01:08:35 +0ms service=bus type=permission.asked publishing
[... 4 permission.asked events at 01:08:35Z ...]
[... silence for 15 minutes ...]
##[error]opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143
```

**Resolution**: Expand bash permission allowlist for `gh` read operations (`gh pr view`, `gh pr diff`, `gh api`, `gh issue`) in subagent permission rulesets. This is a **configuration fix**, not a watchdog fix — the watchdog correctly detected silence.

**Key insight**: The watchdog measures *output absence* as its proxy for idleness. A subagent waiting silently for a permission gate looks identical to a frozen process. There is no distinct signal that separates "waiting for permission" from "stuck in a loop" or "crashed silently."

---

## 6. Approaches That Did Not Work

### 6.1 Increasing Timeout Alone (Band-Aid)

**What was attempted**: Raise `IDLE_TIMEOUT_SECS` from 900 (15 min) to 2700 (45 min) as the sole fix.

**Why it failed**: Doesn't fix the root cause — merely raises the bar. Truly stuck agents waste 45 minutes of runner time before kill. If subagent tasks grow longer, the timeout will need increasing again. Higher Actions minute consumption on failures.

**Status**: Useful as part of a combined approach, but ineffective alone.

### 6.2 Heartbeat File Protocol

**What was attempted**: Have the opencode server periodically write a timestamp to a heartbeat file (e.g., `/tmp/opencode-heartbeat`). The watchdog checks this file's mtime instead of `/proc/io`.

**Why it failed**: Requires modifying opencode server behavior or wrapping it with a heartbeat injector. opencode is a third-party CLI tool — adding heartbeat output requires either a wrapper script that polls the process (complexity) or modifications to opencode itself (not feasible).

**Status**: Elegant but not feasible without opencode architectural changes.

### 6.3 Progress Streaming via `--format json`

**What was attempted**: Configure opencode to emit periodic structured status lines during subagent execution. The watchdog looks for these status lines in the output log instead of relying on raw `/proc/io`.

**Why it failed**: opencode 1.2.24 with `--print-logs` already emits some output, but server-side subagent work is NOT printed to the client's stdout. This would require opencode architectural changes to stream subagent progress to the client.

**Status**: Ideal but blocked by opencode architecture limitations.

### 6.4 Summed Read+Write Bytes

**What was attempted**: Sum `read_bytes + write_bytes` into a single I/O activity signal.

**Why it was abandoned**: Treating reads and writes as equivalent loses diagnostic signal and prevents nuanced idle detection. Background `read_bytes` from unrelated I/O (systemd journal reads, inotify, `/proc` self-reads) can fool the watchdog into thinking a process is active when it's stalled.

**Resolution**: Track read/write separately with different semantics and grace windows.

### 6.5 Process Tree Monitoring

**What was attempted**: Monitor all child processes spawned by the opencode server (`pgrep -P "$root_pid"`), summing their I/O counters.

**Why it was deferred**: Complex implementation (walk `/proc/<pid>/task` or `/proc/<pid>/children`), process tree is ephemeral (short-lived children), performance overhead of scanning many PIDs every 30s. The single-PID split read/write approach solved 95% of cases with far less complexity.

**Status**: Deferred — may be revisited if single-PID monitoring proves insufficient.

### 6.6 Tiered Timeouts by Orchestration Phase

**What was attempted**: Pass the orchestration phase/step as an environment variable to the watchdog. Use longer timeouts for known-slow phases (PR review) and shorter timeouts for fast phases (labeling, commenting).

**Why it was deferred**: Requires phase detection logic in the workflow YAML, adds coupling between workflow steps and watchdog, doesn't scale well as phases change. The split read/write grace window system provides similar benefits with less coupling.

**Status**: Deferred — may be revisited if orchestration phases stabilize and warrant fine-tuning.

---

## 7. Key Learnings for Re-Implementation

### 7.1 Write Bytes Are a Stronger Signal Than Read Bytes

`write_bytes` increasing is hard evidence of genuine progress (database commits, file output, log emission). `read_bytes` increasing can mean many things: API response ingestion (good), polling a queue (maybe bad), or background system reads (noise). **Weight writes more heavily** in idle decisions.

### 7.2 Grace Windows Prevent False Positives

A process doing read-only work (ingesting a large API response, streaming model tokens) should not be killed as quickly as a completely silent process. The `READ_ONLY_GRACE_SECS` window (20 min) provides breathing room for these cases while still catching genuine stalls.

### 7.3 Exit Code Propagation Matters

If you kill a process for idleness, **exit non-zero**. Exiting `0` masks failures in CI systems, causing incomplete runs to appear as "succeeded." This breaks alerting, metrics, and operator trust.

### 7.4 The FIFO Pattern for `tail -f` Cleanup

If you use `tail -f` in any script that runs inside a CI devcontainer, **always** separate the `tail -f` PID from the filter pipeline PID using a named pipe. Without this, cleanup kills will orphan `tail -f`, which holds the cgroup open and causes the workflow to hang indefinitely.

### 7.5 Permission Blocking Looks Like Idleness

A subagent waiting for human permission approval in headless CI produces zero output — indistinguishable from a crashed or frozen process. The watchdog cannot differentiate these cases. **Configuration fixes** (expanding permission allowlists) are required, not watchdog tuning.

### 7.6 Debug Output Should Be Gated

Verbose watchdog diagnostics (`elapsed=`, `read_bytes=`, `write_bytes=`, `write_idle=`, etc.) are invaluable for debugging but add noise to normal runs. Gate behind `DEBUG_ORCHESTRATOR=true`. However, **critical forensics** (server log tail on idle kill) should always be emitted.

### 7.7 Hard Ceiling Catches Edge Cases

The 90-minute hard ceiling catches runs that are technically "active" (small I/O every 14 minutes) but making no real progress. This is a safety net for edge cases the idle detection misses — e.g., a subagent stuck in a retry loop with periodic socket reads.

### 7.8 Test the Watchdog Independently

The repo includes `test/test-watchdog-io-detection.sh` — a standalone test script that validates:
- Constants are set correctly (`IDLE_TIMEOUT_SECS=900`, `READ_ONLY_GRACE_SECS=1200`)
- `_read_server_io_split()` function exists and uses correct awk pattern
- No stale references to old `_read_server_io_bytes()` function
- Simulated `/proc/io` files produce expected output

**Run this test after any watchdog changes** to catch regressions.

---

## 8. Recommended Implementation Order

For a new project implementing the same idle timeout watchdog, follow this phased approach:

### Phase 1 — Basic Idle Detection (Day 1)

| Action | Effort | Impact |
|---|---|---|
| Client output mtime monitoring | 3 lines bash | Detects client silence |
| Server `/proc/<pid>/io` write_bytes monitoring | 10 lines bash | Detects server-side progress |
| 15-minute idle timeout with SIGTERM | 5 lines bash | Kills stalled processes |
| Non-zero exit on idle kill | 2 lines bash | Correct CI failure reporting |

### Phase 2 — Read/Write Split + Grace Windows (Day 2)

| Action | Effort | Impact |
|---|---|---|
| Split `read_bytes` / `write_bytes` tracking | 15 lines bash | Catches network-heavy work |
| `READ_ONLY_GRACE_SECS` window | 5 lines bash | Prevents false positives on read-only phases |
| Tiered idle decision logic | 10 lines bash | Nuanced idle detection |
| Enhanced watchdog messages | 5 lines bash | Operator visibility |

### Phase 3 — Hardening (Day 3)

| Action | Effort | Impact |
|---|---|---|
| SIGKILL escalation after 10s | 4 lines bash | Prevents zombie processes |
| `::error::` annotation on kill | 1 line bash | Prominent failure surfacing |
| Server log tail on idle kill | 3 lines bash | Post-mortem forensics |
| FIFO pattern for `tail -f` cleanup | 10 lines bash | Prevents orphaned processes |
| Hard ceiling timeout | 5 lines bash | Catches edge cases |

### Phase 4 — Testing & Validation (Ongoing)

| Action | Effort | Impact |
|---|---|---|
| Standalone watchdog test script | 50 lines bash | Catches regressions |
| Debug mode gating | 2 lines bash | Reduces noise in normal runs |
| Permission allowlist tuning | As needed | Prevents permission-blocking false positives |

---

## 9. Reference: Configuration Parameters

### 9.1 Timeout Constants

```bash
IDLE_TIMEOUT_SECS=900           # 15 minutes of total I/O silence → kill
READ_ONLY_GRACE_SECS=1200       # 20 minutes with reads-only (no writes) → kill
HARD_CEILING_SECS=5400          # 90-minute absolute safety net
Watchdog interval=30s           # Polling frequency
SIGTERM-to-SIGKILL delay=10s    # Grace period before force-kill
```

### 9.2 Watchdog Output Formats

**Normal mode (client idle, server write-active)**:
```
[watchdog] client output idle 82s, server write I/O active (write_bytes=125829120) — subagent likely running
```

**Normal mode (client idle, server read-only)**:
```
[watchdog] client output idle 145s, server read I/O active (read_bytes=52428800, write_idle=125s/1200s grace) — subagent likely running
```

**Debug mode**:
```
[watchdog] elapsed=886s output_idle=886s server_idle=0s write_active=true read_active=true effective_idle=0s log_size=2847193b log_lines=3847 pid=12345 read_bytes=524288000 write_bytes=146317312 write_idle=15s read_idle=8s
```

**Idle kill**:
```
::error::opencode idle for 15m (no output from client or server); terminating
=== server log tail (last 80 lines before idle kill) ===
...
```

**Hard ceiling kill**:
```
::error::opencode hit 5400s hard ceiling; terminating
```

### 9.3 Exit Codes

| Exit Code | Meaning |
|---|---|
| `0` | Normal completion (all assignments done) |
| `1` | Idle kill, hard ceiling, or explicit failure |
| `143` | SIGTERM received (graceful termination) |
| `137` | SIGKILL received (force-kill after SIGTERM timeout) |

### 9.4 Files to Modify

| File | Purpose |
|---|---|
| `run_opencode_prompt.sh` | Main watchdog loop, `_read_server_io_split()`, termination logic |
| `test/test-watchdog-io-detection.sh` | Standalone watchdog validation tests |
| `.github/workflows/orchestrator-agent.yml` | `DEBUG_ORCHESTRATOR` env var, artifact upload |
| `scripts/post-failure-comment.sh` | Posts watchdog config to GitHub issue on failure |

---

## Appendix: Failure Signature Reference

### A.1 Classic Idle Timeout Kill

```
[watchdog] client output idle 82s, server write I/O active (write_bytes=125829120) — subagent likely running
[watchdog] client output idle 145s, server write I/O active (write_bytes=167772160) — subagent likely running
[watchdog] client output idle 208s, server write I/O active (write_bytes=167772160) — subagent likely running
<silence for 15 minutes — no watchdog messages because write_bytes plateaued>
::error::opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143
=== server log tail (last 80 lines before idle kill) ===
{"level":"DEBUG","msg":"tool_call","tool":"Task","agent":"Code-Reviewer"}
{"level":"DEBUG","msg":"session.created","childSessionId":"ses_xxx"}
<no further activity — subagent blocked on permission approval>
```

### A.2 Permission Blocking (zulu48 Pattern)

```
INFO  2026-03-28T01:08:35 +0ms service=permission permission=bash pattern=gh pr view 5 ...
action={"permission":"bash","pattern":"*","action":"ask"} evaluated
INFO  2026-03-28T01:08:35 +0ms service=bus type=permission.asked publishing
[... 4 permission.asked events at 01:08:35Z ...]
[... silence for 15 minutes ...]
::error::opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143
```

### A.3 Network-Heavy Work (Read-Only Plateau)

```
[watchdog] client output idle 45s, server write I/O active (write_bytes=83886080) — subagent likely running
[watchdog] client output idle 75s, server read I/O active (read_bytes=209715200, write_idle=45s/1200s grace) — subagent likely running
[watchdog] client output idle 105s, server read I/O active (read_bytes=262144000, write_idle=75s/1200s grace) — subagent likely running
<reads continue but writes plateau for 20+ minutes>
::error::opencode idle for 15m (no output from client or server); terminating
opencode exit code: 143
```

---

**Report compiled**: 2026-06-02
**Sources**: See header
**Implementation status**: All phases complete as of commit `22f0b94` (2026-03-28)
