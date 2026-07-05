# N4 Worker Bounded Polling Scheduler Activation Report

Result: `BLOCKED`

Layer role: `N4_trigger`

## Activation

- plist copied: `PASS`
- plutil lint: `PASS`
- launchctl bootstrap: `PASS`
- scheduler loaded: `True`

## Latest Wrapper Report

- path: `docs/N4_WORKER_BOUNDED_POLLING_RUN_ONCE_WRAPPER_REPORT.json`
- result: `BLOCKED`
- blocked_reason: `child_bounded_smoke_runner_failed`
- child_returncode: `1`
- smoke_run_id: `n4_worker_bounded_poll_20260611_20260611T174017+0800`

Root cause: launchd invokes the wrapper successfully, but the wrapper child argv uses relative `python3`; under launchd default PATH that resolves to a Python environment without `psycopg`, so the child bounded smoke runner fails before DB write.

## Boundary Proof

- scoped N4 rows: `{'common_trigger_run': 0, 'common_trigger_quality_item': 0, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}`
- N3 source outbox status: `{'pending': 2100}`
- N3 delivered/delivering: `0`
- downstream refs: `{'common_action_run': 0, 'common_action_event': 0}`
- active wrapper/child process count: `0`

## Stop Status

Stop/unload was not executed because this activation gate only authorized install/enable. The scheduler remains loaded and may continue producing BLOCKED reports every 60 seconds until a stop or repair gate runs.

Next recommended gate: `N4_WORKER_BOUNDED_POLLING_CHILD_PYTHON_ENV_REPAIR_GATE`.
