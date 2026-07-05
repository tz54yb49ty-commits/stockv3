# N1 Condition Source 20260605 Activation Post-Review

Result: `POST_REVIEW_PASS`

- layer_role: `runtime_control`
- source_trade_date: `20260605`
- for_trade_date: `20260608`
- source_batch_id: `condition_source_activation_20260605_v1`

## Execute Proof

Execute report: `docs/N1_condition_source_20260605_activation_execute_report.json`

- result: `EXECUTE_PASS`
- execute_authorized: `true`
- rollback_safe: `true`
- written tables: `common_ingest_batch`, `common_quality_gate_result`, `common_active_source_version`, `stock_daily_basic`, `stock_financial_metrics_fact`, `index_membership_fact`, `board_membership_fact`

## Row Counts

Actual rows match contract, preflight, and execute report:

```json
{
  "stock_daily_basic": 5514,
  "stock_financial": 5514,
  "index_membership": 12841,
  "board_membership": 56962,
  "total": 80831
}
```

Missing identity keys are `0` for all four target tables.

## Active Source Versions

- `stock_daily_basic_20260605_v1`
- `stock_financial_20260605_v1`
- `index_membership_20260605_v1`
- `board_membership_20260605_v1`

All four active versions point to `condition_source_activation_20260605_v1` and were activated by `n1_condition_source_activation_20260605_execute_runner`.

## Quality

- quality rows: `16`
- P0 passed: `12`
- P1 warning: `3`
- P2 warning: `1`
- P0 failed: `0`

Accepted warnings:

- official no-trade excluded from condition universe: `12`
- stale identity manifest only: `1`
- board membership changed from recent active `56960` to current `56962`
- board unmapped raw count filtered: `8`

## Readiness

`scripts/check_condition_source_ready.py --source-trade-date 20260605` now passes.

- missing data types: none
- expected condition stock universe: `5514`
- excluded from condition universe: `0`

## Forbidden Scope Proof

- no Parquet
- no daily bar fact write
- outbox/inbox/checkpoint refs: `0 / 0 / 0`
- N2/N3/N4/N5/N6 refs: `0 / 0 / 0 / 0 / 0`
- no market data pull
- no worker
- no old system touch
- no real trade
- rollback not executed

## Rollback

Rollback SQL: `sql/N1_condition_source_20260605_activation_rollback.sql`

- hard-fail before first `DELETE` / `UPDATE`
- guards outbox / inbox / checkpoint
- guards N2 / N3 / N4 / N5 / N6 refs
- scoped to `condition_source_activation_20260605_v1`
- no `CASCADE`, `DROP`, or `TRUNCATE`

## Decision

N1 condition source activation `20260605` can be marked complete.

Recommended next gate:

`runtime_control N2_CONDITION_LAYER_20260608_READINESS_GATE_FOR_condition_source_activation_20260605_v1`
