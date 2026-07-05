# N4 Worker Bounded Polling Child Python Env Repair Report

Result: `BLOCKED`

Layer role: `N4_trigger`

## Root Cause

The latest scheduled wrapper pass is blocked because the child bounded smoke runner is launched with bare `python3`:

```text
ModuleNotFoundError: No module named 'psycopg'
```

The launchd plist starts the wrapper with an absolute Python that can import `psycopg`, but the wrapper composes the child command with bare `python3`. Under launchd's default `PATH`, that child resolves to a Python environment without `psycopg`.

## Why This Gate Is Blocked

The scheduler is still loaded and fires every 60 seconds with `--execute --user-confirmed`.

If this gate changes the live wrapper to use `sys.executable` now, the next scheduled pass can automatically run the child bounded smoke runner successfully and write scoped N4 database rows. That would violate this gate's constraints:

```text
不手动执行 wrapper
不执行 N4 child runner
不写数据库
不消费/update outbox/inbox/checkpoint
不进入 N5/N6
```

Therefore no code repair was applied in this gate.

## Current Safety Proof

- scheduler label: `com.ashare-v3.n4.bounded-polling`
- scheduler state: loaded, not running between passes
- latest exit code: `2`
- active wrapper/child process: `0`
- latest scoped N4 rows: `0`
- N3 `MarketSnapshotUpdated` pending remains `2100`
- N5/N6 refs remain `0`

## Required Next Gate

`N4_WORKER_BOUNDED_POLLING_SCHEDULER_STOP_OR_PAUSE_GATE`

After stop/pause passes, re-enter:

`N4_WORKER_BOUNDED_POLLING_CHILD_PYTHON_ENV_REPAIR_GATE_RETRY`

Expected repair there:

- update `scripts/run_n4_worker_bounded_poll_once.py`
- child argv uses `sys.executable` or approved absolute Python path
- add tests proving no bare `python3`
- do not execute wrapper/child
- generate repair report
