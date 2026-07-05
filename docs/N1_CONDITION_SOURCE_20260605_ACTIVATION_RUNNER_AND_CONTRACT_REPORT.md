# N1 Condition Source 20260605 Activation Runner And Contract Report

Result: `IMPLEMENTATION_PASS`

- layer_role: `N1_ingestion`
- source_trade_date: `20260605`
- for_trade_date: `20260608`
- source_batch_id: `condition_source_activation_20260605_v1`

## Implementation Summary

Added the 20260605 date-bound N1 condition source activation runner using the verified 20260602 activation mechanics.

- runner module: `src/ashare_v3/ingestion/condition_source_activation_20260605_execute.py`
- runner script: `scripts/run_condition_source_activation_20260605_once.py`
- test: `tests/test_condition_source_activation_20260605_execute.py`
- execute guard: `--execute --user-confirmed --postgres-commit-enabled`
- missing guard blocks before source build / DB write
- execute report persistence: JSON + Markdown

No activation was executed.

## Artifacts

- `docs/N1_condition_source_20260605_activation_dry_run_report.json`
- `docs/N1_CONDITION_SOURCE_20260605_ACTIVATION_DRY_RUN_REPORT.md`
- `docs/N1_condition_source_20260605_activation_execute_contract.json`
- `docs/N1_CONDITION_SOURCE_20260605_ACTIVATION_EXECUTE_CONTRACT.md`
- `docs/N1_condition_source_20260605_activation_execute_preflight.json`
- `docs/N1_CONDITION_SOURCE_20260605_ACTIVATION_EXECUTE_PREFLIGHT.md`
- `docs/N1_condition_source_20260605_activation_execute_report.json`
- `docs/N1_CONDITION_SOURCE_20260605_ACTIVATION_EXECUTE_REPORT.md`
- `sql/N1_condition_source_20260605_activation_rollback.sql`

## Preflight Summary

- result: `PREFLIGHT_PASS`
- runner_readiness: `ready_for_final_gate`
- execute_runner_implemented: `true`
- postgres_commit_implemented: `true`
- execute_authorized: `false`
- final_execute_gate_allowed: `true`
- P0/P1/P2: `0/3/1`

Expected rows:

```json
{
  "stock_daily_basic": 5514,
  "stock_financial": 5514,
  "index_membership": 12841,
  "board_membership": 56962,
  "total": 80831
}
```

Baseline target rows are all `0`; scoped batch and active target source versions are absent.

## Accepted Warnings

- official no-trade condition-source exclusions: `12`
- stale identity manifest only: `1`
- board membership changed from recent active `56960` to current local TDX `56962`, non-blocking P1
- board unmapped raw count filtered: `8` raw / `6` unique, non-blocking P2

## Rollback Proof

Rollback SQL: `sql/N1_condition_source_20260605_activation_rollback.sql`

- hard-fail before first `DELETE` / `UPDATE`
- guards outbox / inbox / checkpoint
- guards N2 / N3 / N4 / N5 / N6 refs
- scoped to `condition_source_activation_20260605_v1`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- rollback not executed

## Validation

- red test failed before implementation with missing module
- `PYTHONPATH=src python3 -m unittest tests/test_condition_source_activation_20260605_execute.py tests/test_condition_source_activation_20260602_execute.py`: `19 OK`
- `python3 -m compileall ...`: `PASS`
- generated JSON parse: `PASS`
- rollback static check: `PASS`
- `git diff --check`: `PASS`

## Forbidden Scope Proof

- no activation execute
- no DB write
- no Parquet
- no daily bar fact write
- no outbox/inbox/checkpoint consumption or update
- no N2/N3/N4/N5/N6 entry
- no market data pull
- no worker
- no rollback execution
- no old system touch
- no real trade

## Next Gate

`runtime_control N1_CONDITION_SOURCE_20260605_ACTIVATION_EXECUTE_FINAL_GATE_REVIEW`
