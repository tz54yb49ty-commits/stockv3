# N3 After N2-R3 Market Data Subscription Rebuild Report

Date: 2026-05-24T21:10:50
Layer: N3_market_data
Mode: subscription_pull_plan_control_execute_only
Status: passed

## Summary

```text
market_data_run_id = market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524205747_execute
source_condition_run_id = condition_layer_20260522_to_20260525_20260524205747_execute
condition_run_status = passed
market_run_status = passed
P0/P1/P2 = 0/1/0
```

## Old Dependency Audit

- old N3 runs based on other condition runs: `2`
- N4 outbox condition-run reference groups: `2`

Old dependency rows were reported only; no N4/N5/N6 rows were changed.

## Scope And Subscription Counts

| item | stock | index | board | total |
|---|---:|---:|---:|---:|
| N2 scope rows | 4236 | 18 | 258 | 4512 |
| N2 scope objects | 2052 | 9 | 127 | 2188 |
| subscription objects | 2052 | 9 | 127 | 2188 |

```text
candidate_rows = 13536
subscription_rows = 6564
pull_plan_rows = 9
required_data_kind_counts = {"minute_bar_1m": {"rows": 2188, "objects": 2188}, "previous_day_minute_bar_1m": {"rows": 2188, "objects": 2188}, "realtime_daily_snapshot": {"rows": 2188, "objects": 2188}}
```

## Previous-Day Minute Date

```text
previous_day_minute_subscription_dates = {"20260522": {"rows": 2188, "objects": 2188}}
previous_day_pull_plan_dates = {"20260522": {"rows": 3, "object_count_sum": 2188}}
previous_day_mismatch_count = 0
```

## Outbox / Facts

```text
common_event_outbox before = 26652
common_event_outbox after = 26652
common_event_outbox rows for this N3 run = 0
market_facts_and_events_unchanged = true
```

## Checks

```text
condition_run_passed = true
condition_run_p0_zero = true
market_run_created_once = true
market_run_status_passed = true
market_run_p0_zero = true
source_condition_run_id_matches = true
source_scope_row_count_matches = true
candidate_row_count_matches = true
subscription_row_count_matches = true
subscription_object_count_matches = true
pull_plan_row_count_matches = true
previous_day_minute_date_20260522 = true
previous_day_pull_plan_date_20260522 = true
pull_plan_execute_allowed_false = true
common_event_outbox_unchanged = true
common_event_outbox_no_rows_for_n3_run = true
market_facts_and_events_unchanged = true
no_market_data_pull_flags = true
rollback_sql_generated = true
```

## Rollback

Rollback SQL: `sql/N3_after_N2_R3_market_data_subscription_rollback.sql`

Rollback was generated but not executed.

## Boundary

```text
old_system_touched: no
external_market_api_called: no
market_data_pulled: no
market_data_fact_written: no
common_event_outbox_written: no
entered_N4_N5_N6: no
worker_started: no
n2_condition_modified: no
n1_fact_modified: no
```

## Artifacts

- execute_report_json: `docs/N3_AFTER_N2_R3_market_data_subscription_execute_report.json`
- execute_report_md: `docs/N3_AFTER_N2_R3_MARKET_DATA_SUBSCRIPTION_EXECUTE_REPORT.md`
- pre_backup: `backups/N3_after_N2_R3_subscription_execute_before_20260524.json`
- post_backup: `backups/N3_after_N2_R3_subscription_execute_after_20260524.json`
- precheck_baseline: `backups/N3_after_N2_R3_subscription_precheck_baseline_20260524.json`
- dry_run_json: `tmp/N3_after_N2_R3_subscription_dry_run.json`
- rollback_sql: `sql/N3_after_N2_R3_market_data_subscription_rollback.sql`

## Next Step

Stop here. Do not pull market data or enter N4/N5/N6 without explicit user confirmation.
