# 20260601 A1 Opening Prep Completion Report

Result: `PARTIAL_PASS_WITH_DATE_BLOCKER`

This report covers only A1 opening-prep work directly related to N1/N2/N3. It
does not enter N4/N5/N6, does not start a worker, and does not touch old-system,
voice, mobile, sim, or real-trading state.

## Summary

```text
N1 readiness/source/calendar = PASS
N1 archive traceability      = TRACEABLE_NOT_SEALED
N2 latest active             = condition_layer_20260529_source_20260529_v6
N3 subscription              = PASS
N3 previous-day preload      = PASS
N3 B1 snapshot readiness     = BLOCKED only by current_date_after_for_trade_date
current_date                 = 20260602
for_trade_date               = 20260601
```

## N1

Readiness artifacts refreshed:

- `docs/N1_A1_real_execution_readiness_20260601.json`
- `docs/N1_A1_parquet_readiness_20260601.json`
- `docs/N1_A1_schema_readiness_20260601.json`
- `docs/N1_A1_environment_probe_artifact_20260601.json`
- `docs/N1_A1_environment_probe_20260601.json`
- `docs/N1_A1_condition_source_ready_20260529_for_20260601.json`
- `docs/N1_A1_real_execution_application_20260601.json`
- `docs/N1_A1_daily_incremental_acceptance_20260529_for_20260601.json`
- `docs/N1_A1_ingestion_batch_archive_plan_20260529_for_20260601.json`

20260601 calendar patch:

```text
source_batch_id = trade_calendar_20260601_patch_v1
source_version  = trade_calendar_20260601_patch_v1
trade_date      = 20260601
is_open         = true
prev_trade_date = 20260529
next_trade_date = 20260602
source          = tushare.trade_cal.patch
quality         = P0 passed 11
```

Artifacts:

- `docs/N1_trade_calendar_20260601_patch_preflight.json`
- `docs/N1_TRADE_CALENDAR_20260601_PATCH_PREFLIGHT.md`
- `sql/N1_trade_calendar_20260601_patch_rollback.sql`

Boundary:

```text
daily facts touched = false
condition_* touched = false
outbox/inbox/checkpoint unchanged = 151341 / 56170 / 4368
N2/N3/N4/N5/N6 touched by calendar patch = false
```

Rollback note:

`sql/N1_trade_calendar_20260601_patch_rollback.sql` is intentionally guarded.
Because existing N2/N3 rows already reference `20260601`, rollback should be
treated as blocked unless those downstream refs are rolled back first.

Archive traceability:

```text
result = TRACEABLE_NOT_SEALED
subscription/preload lineage = traceable
B1 snapshot rows = 0
sealed runtime archive_request = not available
```

Artifacts:

- `docs/A1_RUNTIME_ARCHIVE_TRACEABILITY_20260601.md`
- `docs/A1_runtime_archive_traceability_20260601.json`

## N2

Current active run:

```text
run_id = condition_layer_20260529_source_20260529_v6
status = passed_active
previous v5 status = superseded
source_trade_date / for_trade_date / prev_trade_date = 20260529 / 20260601 / 20260529
P0/P1/P2 = 0/6/3
```

Rows:

```text
condition_basis:         stock=5506 index=83  board=428
condition_pool:          stock=4106 index=187 board=942
minute_target_scope:     stock=4087 index=187 board=942
condition_display_basis: stock=1862 index=83  board=428
monitor_target:          stock=5506 index=83  board=428
```

N3 handoff:

```text
source_condition_run_id = condition_layer_20260529_source_20260529_v6
n3_lineage_auto_switch  = false
handoff consumed by N3 subscription run = true
```

## N3

Subscription:

```text
run_id = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
status = passed
P0/P1/P2 = 0/1/0
candidate/subscription/pull_plan/quality = 6162 / 3319 / 9 / 34
market_data_pulled = false
market_data_fact_written = false
downstream_layers_touched = false
worker_started = false
```

Previous-day preload:

```text
run_id = previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
status = passed
P0/P1/P2 = 0/1/0
stock/index/board minute rows = 87840 / 5040 / 20640
stock/index/board status rows = 366 / 21 / 86
downstream_layers_touched = false
worker_started = false
```

B1 snapshot readiness after calendar patch:

```text
actual current_date readiness:
  ready = false
  blocked_reason = current_date_after_for_trade_date
  calendar row_count = 1
  calendar is_open = true
  snapshot existing rows = 0
  outbox existing rows = 0

as-of 20260601 readiness:
  ready = true
  P0/P1/P2 = 0/0/0
```

Artifacts:

- `docs/N3_B1_realtime_snapshot_20260601_execute_readiness_after_calendar_patch.json`
- `docs/N3_B1_REALTIME_SNAPSHOT_20260601_EXECUTE_READINESS_AFTER_CALENDAR_PATCH.md`
- `docs/N3_B1_realtime_snapshot_20260601_execute_readiness_asof_20260601.json`
- `docs/N3_B1_REALTIME_SNAPSHOT_20260601_EXECUTE_READINESS_ASOF_20260601.md`

## Remaining Blocker

`N3-B1 realtime_daily_snapshot` cannot be executed now because the actual
current date is `20260602`, while the contract requires execution on
`for_trade_date=20260601`.

This is a runtime-date blocker, not a missing N1/N2/N3 artifact blocker. The
calendar/source/subscription/preload/runner gates are otherwise ready as shown
by the as-of readiness artifact.

## Boundary

```text
N4/N5/N6 entered = false
worker_started = false
voice/mobile/sim/real_trade touched = false
old_system touched = false
outbox/inbox/checkpoint = 151341 / 56170 / 4368
```
