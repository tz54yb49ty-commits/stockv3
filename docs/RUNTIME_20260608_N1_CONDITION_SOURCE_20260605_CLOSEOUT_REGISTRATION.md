# Runtime 20260608 N1 Condition Source 20260605 Closeout Registration

result = CLOSEOUT_PASS

This is a runtime_control registration only. It did not execute SQL, did not execute rollback, did not enter N2/N3/N4/N5/N6, did not pull market data, and did not start a worker.

## Execute Summary

```text
source_trade_date = 20260605
source_batch_id = condition_source_activation_20260605_v1
execute_status = EXECUTE_PASS
post_review = POST_REVIEW_PASS
```

| Table | Rows |
|---|---:|
| stock_daily_basic | 5514 |
| stock_financial_metrics_fact | 5514 |
| index_membership_fact | 12841 |
| board_membership_fact | 56962 |
| total | 80831 |

```text
common_ingest_batch = 1
common_quality_gate_result = 16
common_active_source_version = 4
```

## Active Source Versions

```text
stock_daily_basic = stock_daily_basic_20260605_v1
stock_financial = stock_financial_20260605_v1
index_membership = index_membership_20260605_v1
board_membership = board_membership_20260605_v1
```

## Condition Source Ready Proof

```text
condition_source_ready = true
missing_data_types = []
expected_condition_stock_universe = 5514
excluded_from_condition_universe = 0
identity_coverage_100pct = true
```

## Quality Summary

```text
P0_failed = 0
P1_warning = 3
P2_warning = 1
official_no_trade_excluded_from_condition_universe = 12
stale_stock_identity_manifest_only = stock:SZ:300114
board_unmapped_raw_filtered = 8
```

## Boundary Proof

```text
official_daily_rows_unchanged = stock/index/board 5514/83/428
daily_bar_fact_rows_written_by_condition_source_batch = 0/0/0
outbox/inbox/checkpoint refs = 0/0/0
N2/N3/N4/N5/N6 refs = 0/0/0/0/0
market_data_pulled = false
parquet_written = false
worker_started = false
old_system_touched = false
real_trade = false
```

## Rollback Summary

```text
rollback_sql_path = sql/N1_condition_source_20260605_activation_rollback.sql
rollback_safe = true
hard_fail_before_delete_or_update = true
guards_outbox_inbox_checkpoint = true
guards_n2_n3_n4_n5_n6_refs = true
scope_only_condition_source_activation_20260605_v1 = true
no_CASCADE_DROP_TRUNCATE = true
rollback_executed = false
```

## Runtime Control Scope

```text
database_written_by_runtime_control = false
registry_command_executed = false
rollback_executed = false
n2_executed = false
n3_entered = false
```

Next gate: `N2_CONDITION_LAYER_20260608_EXECUTE_USER_CONFIRMATION_GATE`.
