# V3 Phase 1 Common Bounded Worker Control Contract

## Scope

PR-1.1 only extends common bounded worker control utilities under `src/ashare_v3/runtime`.

It does not implement N3, N4, or N5 worker wrappers. It does not execute N3/N4/N5/N6, write database rows, modify SQL, start schedulers or workers, call market adapters, or touch trade/sim/voice/mobile paths.

PR-1.1 is a public utility contract only. Layer-specific wrappers remain deferred.
N3/N4/N5 bounded wrappers are not implemented in this PR.

## Provided Utilities

- `BoundedResult`: `PASS`, `NOOP`, `PARTIAL`, `BLOCKED`, `CRASHED`, `UNKNOWN_AFTER_TIMEOUT`, `COMMIT_UNKNOWN`.
- `BoundedWorkerConfig`: immutable common worker invocation config.
- `BoundedWorkerStatus`: status payload builder with `to_dict()`.
- `SingletonLockHeld`: raised when a singleton lock is already held.
- `build_invocation_id()`: UUID4 hex invocation id.
- `build_run_id(prefix, trade_date, invocation_id=None, now=None)`: safe prefix, strict `YYYYMMDD` trade date, UTC microsecond timestamp, and UUID suffix. Run IDs are not minute-only.
- `build_phase1_realtime_chain_lock_path(repo_root, trade_date)`: shared Phase 1 N3/N4/N5 realtime chain lock path builder. It returns `<repo_root>/tmp/v3_phase1_realtime_chain_<trade_date>.lock`, validates `trade_date`, and does not create files, create directories, or acquire locks.
- `acquire_global_chain_lock(lock_path, metadata)`: non-blocking file lock for one trade-date chain on one host and one visible filesystem.
- `check_stop_file(stop_file)`: cooperative stop-file helper.
- `deadline_from_now(max_runtime_seconds, now=None)` and `remaining_deadline_seconds(deadline, now=None)`: deadline helpers.
- `run_child_with_timeout(argv, timeout_seconds, cwd=None, env=None)`: child subprocess timeout wrapper.
- `atomic_write_json(path, payload)`: temp-file write, fsync, atomic replace.
- `result_to_exit_code(result)`: process exit-code contract.

## Exit Code Contract

| result | exit_code |
|---|---:|
| `PASS` | 0 |
| `NOOP` | 0 |
| `PARTIAL` | 2 |
| `BLOCKED` | 2 |
| `CRASHED` | 1 |
| `UNKNOWN_AFTER_TIMEOUT` | 3 |
| `COMMIT_UNKNOWN` | 3 |

## Status Invariant Contract

`BoundedWorkerStatus` enforces post-check invariants in code and fails closed with `ValueError` for unknown results or illegal combinations:

| result | requires_post_check |
|---|---|
| `PASS` | `false` |
| `NOOP` | `false` |
| `PARTIAL` | `false` |
| `BLOCKED` | `false` |
| `CRASHED` | `false` |
| `UNKNOWN_AFTER_TIMEOUT` | `true` |
| `COMMIT_UNKNOWN` | `true` |

`CRASHED` means the child exited with a known non-zero result and defaults to `requires_post_check=false`. If a commit or connection ambiguity exists, callers must use `COMMIT_UNKNOWN` instead.

`PARTIAL` means at least one stage in a bounded plan is known to have completed successfully, but the complete plan did not finish. It is not a crash and is not a zero-write blocker. It has exit code `2`, requires `requires_post_check=false`, and does not authorize downstream consumption.

When `result=PARTIAL`, `BoundedWorkerStatus` fails closed with `ValueError` unless all of these are true:

- `completed_stages` is non-empty.
- `pending_stages` is non-empty.
- `completed_stages` and `pending_stages` do not overlap.
- neither stage list contains duplicates.
- `partial_reason` is a non-empty string.
- `output_run_ids` is present and non-empty.
- `rollback_artifacts` is present and non-empty.
- `downstream_consumption_allowed=false`.

The common runtime field is `downstream_consumption_allowed`. N3-specific `n4_consumption_allowed` is not part of PR-1.1; a later N3 wrapper or manifest may map `PARTIAL` to `n4_consumption_allowed=false`.

## Singleton Contract

The global chain lock uses `fcntl.flock` on a file path.

`build_phase1_realtime_chain_lock_path(repo_root, trade_date)` provides the shared Phase 1 N3/N4/N5 path:

```text
<repo_root>/tmp/v3_phase1_realtime_chain_<trade_date>.lock
```

The filename intentionally does not contain layer-specific `n3`, `n4`, or `n5` names. Future N3/N4/N5 wrappers must reuse this builder to share the same lock path. The builder only constructs a `Path`; it does not create files, create directories, or acquire the lock.

- The first process obtains the lock.
- A second process on the same host and same visible filesystem receives `NOOP` with `stop_reason=singleton_lock_held` and exit code `0`.
- The second process must not invoke child commands.
- The second process must not overwrite the first process lock metadata.

Deployment assumption: Phase 1 singleton safety is only guaranteed when all of these are true:

- single host
- same visible filesystem
- all related entrypoints follow this same lock protocol

Legacy scripts, manual SQL, or entrypoints that do not follow the protocol cannot be stopped by this file lock. Cross-host, multi-node container, or different-filesystem deployment is `BLOCKED` until a database advisory lock, scheduler lease, or equivalent cross-host lock is approved.

## Timeout Contract

If a child subprocess times out before commit knowledge is available:

- result is `UNKNOWN_AFTER_TIMEOUT`
- exit code is `3`
- `requires_post_check=true`
- no automatic retry is allowed
- no automatic rollback is allowed
- caller must run an explicit post-check gate

`run_child_with_timeout` uses `subprocess.Popen`. On POSIX/macOS it starts the child in a new session and terminates the whole process group on timeout: first `SIGTERM`, then bounded grace waiting, then `SIGKILL` if the process group still has not exited. The direct child is always reaped with `communicate()` or `wait()` semantics, and stdout/stderr are captured safely.

Process-group termination cleans up descendants that remain in the same session/process group. Descendants that actively call `setsid`, daemonize, or otherwise detach from that process group are outside this guarantee.

`UNKNOWN_AFTER_TIMEOUT` means the child was killed by runtime timeout and external commit status cannot be confirmed. `COMMIT_UNKNOWN` means a known commit or connection ambiguity occurred and is not necessarily timeout-related. Both have exit code `3`, require post-check, and never authorize automatic retry or automatic rollback.

## Status JSON Contract

Status JSON is written with a temp file and atomic rename. Each invocation must use a non-colliding status path or invocation-specific filename so one invocation does not overwrite another invocation's status.

`atomic_write_json` writes the temporary file in the target directory, flushes and fsyncs the temporary file, uses `os.replace`, fsyncs the parent directory after replace, removes temporary files on error, and serializes JSON with stable sorted keys. It does not automatically include sensitive environment variables or unnecessary absolute repository paths in the payload.

Required payload fields:

```json
{
  "result": "NOOP",
  "stop_reason": "singleton_lock_held",
  "requires_post_check": false,
  "invocation_id": "...",
  "run_id": "...",
  "trade_date": "YYYYMMDD",
  "worker_name": "phase1_chain",
  "input_run_ids": {},
  "output_run_id": null,
  "completed_stages": [],
  "pending_stages": [],
  "partial_reason": null,
  "output_run_ids": {},
  "rollback_artifacts": {},
  "downstream_consumption_allowed": false,
  "git_sha": "...",
  "config_hash": "...",
  "processed_count": 0,
  "written_count": 0,
  "skipped_count": 0,
  "blocked_count": 0,
  "external_side_effects": {
    "db_write": false,
    "worker_started": false,
    "n6_writes": 0,
    "real_trade_api_calls": 0,
    "sim_writes": 0,
    "voice_writes": 0,
    "mobile_writes": 0
  }
}
```

PR-1.1 only provides the status builder, writer, `PARTIAL` contract, and shared lock path builder. N3/N4/N5 integration is deferred.

## Non-Changes

PR-1.1 does not modify:

- `scripts/*`
- `src/ashare_v3/market/*`
- `src/ashare_v3/trigger/*`
- `src/ashare_v3/action/*`
- `sql/*`
- N6 files
- database schema or migrations
- runtime worker execution paths

PR-1.1 does not execute rollback, migration, DB write, worker/scheduler, market adapter, or trade/sim/voice/mobile paths. It does not change the `UNKNOWN_AFTER_TIMEOUT` or `COMMIT_UNKNOWN` contracts.
