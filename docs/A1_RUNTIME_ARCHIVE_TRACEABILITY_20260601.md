# A1 Runtime Archive Traceability 20260601

Result: `TRACEABLE_NOT_SEALED`

This is a read-only N1/N3 traceability review. It does not write Parquet,
does not create an archive request, does not start a worker, and does not enter
N4/N5/N6.

## Lineage

```text
source_condition_run_id = condition_layer_20260529_source_20260529_v6
subscription_run_id     = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
previous_day_preload    = previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
snapshot_run_id         = realtime_snapshot_20260601_market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
```

## Traceable Runtime Data

```text
subscription_candidate = 6162
subscription           = 3319
pull_plan              = 9
quality_item           = 34

previous-day minute rows:
  stock = 87840
  index = 5040
  board = 20640

previous-day preload status rows:
  stock = 366
  index = 21
  board = 86
```

Rollback paths:

```text
subscription rollback        = sql/N3_subscription_20260601_rollback.sql
previous-day preload rollback = sql/N3_A1_previous_day_minute_20260529_rollback.sql
snapshot rollback contract    = sql/N3_B1_realtime_snapshot_20260601_rollback.sql
```

## Not Sealed

```text
stock_realtime_daily_snapshot rows = 0
index_realtime_daily_snapshot rows = 0
board_realtime_daily_snapshot rows = 0
scoped outbox rows = 0
scoped inbox rows = 0
```

Reason:

```text
B1 realtime snapshot has not executed.
Actual B1 readiness is blocked by current_date_after_for_trade_date:
current_date=20260602, for_trade_date=20260601.
```

Therefore no sealed runtime partition or archive_request can be truthfully
created for the 20260601 B1 snapshot lineage in this run.

## N1 Archive Readiness

Readiness/plan artifacts:

```text
docs/N1_A1_real_execution_application_20260601.json
docs/N1_A1_daily_incremental_acceptance_20260529_for_20260601.json
docs/N1_A1_ingestion_batch_archive_plan_20260529_for_20260601.json
docs/N1_A1_parquet_readiness_20260601.json
```

These prove N1 archive planning/readiness is available for raw-ingestion
datasets. They do not replace the missing N3 sealed runtime archive_request.

## Boundary

```text
writes_performed = false
parquet_written = false
archive_request_written = false
worker_started = false
N4/N5/N6 entered = false
old_system_touched = false
real_trading_touched = false
```
