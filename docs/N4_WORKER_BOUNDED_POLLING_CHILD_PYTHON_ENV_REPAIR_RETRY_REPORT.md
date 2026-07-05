# N4 Worker Bounded Polling Child Python Env Repair Retry Report

Result: `FIX_PASS`

Layer role: `N4_trigger`

## Root Cause

The scheduler activation pass previously blocked because the wrapper child argv used bare `python3`. Under launchd's default `PATH`, that child resolved to a Python environment without `psycopg`, producing:

```text
ModuleNotFoundError: No module named 'psycopg'
```

## Code Repair

Updated `scripts/run_n4_worker_bounded_poll_once.py` so the child bounded smoke runner defaults to the wrapper runtime Python:

```text
sys.executable
```

The explicit `--python-executable` override remains available for a separately approved absolute Python path. The default is no longer bare `python3`.

## Child Python Env Proof

- Default child Python comes from `sys.executable`.
- Tests assert the child argv does not use bare `python3`.
- The launchd plist still preserves `PYTHONPATH=src:scripts`.
- No wrapper or child runner was manually executed in this gate.

## Validation

- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_poll_once` -> PASS, 6 tests OK.
- `PYTHONPATH=src:scripts python3 -m unittest tests.test_n4_worker_bounded_poll_once tests.test_n4_worker_bounded_smoke tests.test_n4_worker_state_transition` -> PASS, 43 tests OK.
- Parser default `--python-executable` equals `sys.executable` -> PASS.

## Forbidden Scope Proof

This gate did not load scheduler, manually execute wrapper, execute the N4 child runner, write the database, consume/update outbox/inbox/checkpoint, enter N5/N6, start a worker, or touch delivery, push, voice, mobile, sim, position, order, trade, real trade, or the old system.

Next gate: `N4_WORKER_BOUNDED_POLLING_CHILD_PYTHON_ENV_REPAIR_POST_REVIEW_GATE`.
