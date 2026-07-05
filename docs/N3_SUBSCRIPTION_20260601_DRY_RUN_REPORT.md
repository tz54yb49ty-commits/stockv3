# N3 Subscription 20260601 Dry-Run Report

## Result

```text
DRY_RUN_PASS
layer_role = N3_market_data
source_condition_run_id = condition_layer_20260529_source_20260529_v6
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
writes_performed = false
market_data_pulled = false
market_data_fact_written = false
downstream_layers_touched = false
worker_started = false
```

## Row Counts

```text
source_scope_row_count = 5216
source_scope_row_count_by_asset_kind = stock=4087, index=187, board=942
source_scope_object_count_by_asset_kind = stock=1862, index=83, board=428
subscription_candidate_count = 6162
dedup_subscription_count = 3319
subscription_object_count = 2373
object_count_by_asset_kind = stock=1862, index=83, board=428
market_data_pull_plan_row_count = 9
```

## Required Data Kinds

```text
realtime_daily_snapshot = 2373
minute_bar_1m = 473
previous_day_minute_bar_1m = 473
previous_day_minute_date_counts = 20260529:473
previous_day_minute_required_by_asset_kind = stock=366, index=21, board=86
```

## Quality

```text
P0/P1/P2 = 0/1/0
```

P1 warning:

```text
common_trade_calendar detail row for 20260601 is missing.
```

This does not block N3 subscription control-row planning. Later N3-B1 realtime snapshot readiness must re-check the 20260601 calendar row and block if it is still missing.

## Artifacts

```text
dry_run_json = docs/N3_subscription_20260601_from_N2_v6_dry_run_report.json
```
