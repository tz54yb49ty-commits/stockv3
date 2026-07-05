# N1 20260605 Close And 20260608 Calendar Repair Contract

result: `CONTRACT_PASS`

layer_role: `runtime_control`

## Purpose

Prepare the N1 repair path required before the requested 20260608 premarket chain can continue:

```text
N1 -> N2 -> N3 subscription -> N3-A1 previous-day minute preload
```

Requested lineage:

```text
source_trade_date=20260605
for_trade_date=20260608
previous_trade_date=20260605
current_date=20260607
```

This contract does not execute writes. It only defines the N1 repair scope, rollback registry, and follow-up gates.

## Repair Scope

Calendar patch:

```text
trade_date=20260608
expected_prev_trade_date=20260605
fallback_next_trade_date=20260609
source_batch_id=trade_calendar_20260608_patch_v1
source_version=trade_calendar_20260608_patch_v1
```

Allowed future write scope after N1 final gate and explicit user confirmation:

```text
common_ingest_batch
common_trade_calendar
common_active_source_version
common_quality_gate_result
```

Official daily ingestion:

```text
trade_date=20260605
source_batch_id=official_daily_ingest_20260605_v1
stock_daily=stock_daily_20260605_v1
index_daily=index_daily_20260605_v1
board_daily=board_daily_20260605_v1
```

Allowed future write scope after N1 final gate and explicit user confirmation:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

Condition source activation:

```text
trade_date=20260605
source_batch_id=condition_source_activation_20260605_v1
stock_daily_basic=stock_daily_basic_20260605_v1
stock_financial=stock_financial_20260605_v1
index_membership=index_membership_20260605_v1
board_membership=board_membership_20260605_v1
```

Allowed future write scope after N1 final gate and explicit user confirmation:

```text
common_ingest_batch
common_quality_gate_result
common_active_source_version
stock_daily_basic
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
```

## Live Baseline

| Check | Value |
|---|---:|
| calendar_20260608_rows | 0 |
| calendar_20260608_active_conflicts | 0 |
| calendar_patch_batch_conflicts | 0 |
| official_daily_batch_conflicts | 0 |
| condition_source_batch_conflicts | 0 |
| stock_daily_bar_fact_20260605_rows | 0 |
| index_daily_bar_fact_20260605_rows | 0 |
| board_daily_bar_fact_20260605_rows | 0 |
| stock_daily_basic_20260605_rows | 0 |
| stock_financial_metrics_fact_20260605_rows | 0 |
| index_membership_fact_20260605_rows | 0 |
| board_membership_fact_20260605_rows | 0 |
| N2 refs | 0 |
| N3 refs | 0 |
| N4 refs | 0 |
| N5 broad refs | 0 |

## Runner Notes

`scripts/run_trade_calendar_patch_once.py` supports guarded calendar execution with:

```text
--execute
--user-confirmed
--postgres-commit-enabled
```

The generic daily runner `scripts/run_real_daily_incremental.py` is a real write runner. It does not present the same final-gate CLI guard model as later governed runners. The N1 final gate must either approve the generic runner path explicitly or first generate a date-specific guarded 20260605 runner.

No date-specific 20260605 condition-source runner was confirmed in this gate.

## Rollback Registry

| Stage | Rollback SQL | Scope |
|---|---|---|
| calendar_patch | `sql/N1_trade_calendar_20260608_patch_rollback.sql` | only `trade_calendar_20260608_patch_v1` rows |
| official_daily_ingestion | `sql/N1_official_daily_20260605_ingestion_rollback.sql` | only `official_daily_ingest_20260605_v1` rows |
| condition_source_activation | `sql/N1_condition_source_20260605_activation_rollback.sql` | only `condition_source_activation_20260605_v1` rows |

All rollback drafts hard-fail before the first `DELETE` or `UPDATE` and block if downstream refs exist.

## Forbidden Scope

This gate does not allow:

- N2 condition execute
- N3 subscription execute
- N3-A1 preload execute
- realtime snapshot or today minute pull
- N4/N5/N6
- outbox/inbox/checkpoint consumption or mutation
- worker
- delivery/push/voice/mobile
- sim/position/PnL/real trade
- proposal/order/trade
- old system access

## Next Gate

```text
N1_20260605_CLOSE_AND_20260608_CALENDAR_REPAIR_EXECUTE_FINAL_GATE_REVIEW
```

