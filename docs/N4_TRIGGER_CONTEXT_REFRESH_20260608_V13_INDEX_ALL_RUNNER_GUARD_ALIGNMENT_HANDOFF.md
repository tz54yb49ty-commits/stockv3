# N4 Trigger Context Refresh 20260608 v13 Index-All Runner Guard Alignment Handoff

- handoff_result: `WAIT_N4_TRIGGER_RUNNER_GUARD_ALIGNMENT`
- layer_role: `runtime_control`
- next_layer_role: `N4_trigger`
- next_required_gate: `N4_TRIGGER_CONTEXT_REFRESH_RUNNER_GUARD_ALIGNMENT_GATE_FOR_20260608_V13_INDEX_ALL`

## Evidence

- alignment report exists: `false`
- runner has `--execute`: `false`
- runner has `--user-confirmed`: `false`
- common_trigger_run rows: `0`
- context rows stock/index/board: `0/0/0`
- context preflight result: `PASS`
- planned context rows: `4677`
- planned objects stock/index/board: `1945/83/127`

## Blocker

`P0 n4_context_refresh_runner_manual_confirmation_guard_missing`

The N4 context refresh writer lacks explicit `--execute` and `--user-confirmed` guards, so runtime_control cannot allow the execute user confirmation point.

## Required Alignment

Update `scripts/run_trigger_context_snapshot_execute.py` so it:

- supports `--execute`
- supports `--user-confirmed`
- blocks before DB write when either flag is missing
- keeps legacy arguments compatible:
  - `--condition-run-id`
  - `--for-trade-date`
  - `--json-report-path`
  - `--markdown-report-path`
  - `--rollback-sql-path`

## Forbidden Scope Proof

- runtime_control did not modify the runner.
- runtime_control did not execute N4 context refresh.
- DB written: `false`
- rollback executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- worker started: `false`
- N5/N6 entered: `false`
