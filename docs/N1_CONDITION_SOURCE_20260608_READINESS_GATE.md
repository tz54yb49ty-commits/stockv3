# N1 Condition Source 20260608 Readiness Gate

Result: `BLOCKED`

- layer_role: `runtime_control`
- source_trade_date: `20260605`
- for_trade_date: `20260608`
- target batch: `condition_source_activation_20260605_v1`

## Summary

N1 official daily ingestion for `20260605` is complete and post-reviewed, but the N1 condition source activation required before N2 is not complete.

The read-only readiness check blocks on missing active condition-source inputs:

- `stock_daily_basic`
- `stock_financial`
- `index_membership`
- `board_membership`

The repository currently has rollback SQL for `20260605`, but no matching activation runner/script or contract/preflight artifacts.

## N1 Official Daily Proof

- post-review result: `POST_REVIEW_PASS`
- execute result: `EXECUTE_PASS`
- source batch: `official_daily_ingest_20260605_v1`
- stock/index/board daily rows: `5514 / 83 / 428`
- total daily rows: `6025`
- active versions:
  - `stock_daily_20260605_v1`
  - `index_daily_20260605_v1`
  - `board_daily_20260605_v1`
  - `stock_identity_20260605_v1`
- no-trade manifest count: `12`
- `stock:SZ:000638` included in no-trade manifest and has `0` fact rows

## Readiness Check

Command:

```bash
PYTHONPATH=src python3 scripts/check_condition_source_ready.py --source-trade-date 20260605
```

Result: `passed=false`, exit code `2`.

Daily active inputs are present and identity coverage is complete:

- `stock_daily_20260605_v1`: `5514`
- `index_daily_20260605_v1`: `83`
- `board_daily_20260605_v1`: `428`

Missing data types:

- `stock_daily_basic`
- `stock_financial`
- `index_membership`
- `board_membership`

## Target Baseline

- `common_ingest_batch`: `0`
- `common_quality_gate_result`: `0`
- `stock_daily_basic`: `0`
- `stock_financial_metrics_fact`: `0`
- `index_membership_fact`: `0`
- `board_membership_fact`: `0`

## Artifact Inventory

- runner module: missing
- runner script: missing
- execute contract: missing
- execute preflight: missing
- execute report: missing
- rollback SQL: present at `sql/N1_condition_source_20260605_activation_rollback.sql`

## Rollback Proof

Rollback SQL is present and statically hardened:

- hard-fail before first `DELETE`
- guards outbox / inbox / checkpoint refs
- guards N2 / N3 / N4 / N5 / N6 refs
- scoped to `condition_source_activation_20260605_v1`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- rollback not executed

## Forbidden Scope Proof

This gate was read-only:

- no DB write
- no condition source execute
- no N2/N3/N4/N5/N6 entry
- no market data pull
- no outbox/inbox/checkpoint consumption or update
- no worker
- no rollback execution
- no old system touch
- no real trade

## Next Gate

`blocked_by_layer=N1_ingestion`

Recommended next gate:

`N1_CONDITION_SOURCE_20260605_ACTIVATION_RUNNER_AND_CONTRACT_GATE`

Purpose: implement or generate the `20260605` condition source activation runner, contract, dry-run, preflight, and execute final gate artifacts before any N2/N3 work.
