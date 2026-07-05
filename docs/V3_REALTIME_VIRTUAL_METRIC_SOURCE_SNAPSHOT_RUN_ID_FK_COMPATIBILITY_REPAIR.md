# V3 Realtime Virtual Metric Source Run ID FK Compatibility Repair

Result: `REPAIR_PASS`

Layer: `N3_market_data`

This gate repairs writer/artifact compatibility only. It did not execute the
writer, did not write database rows, did not execute rollback, did not consume
or update event infrastructure, and did not enter N4/N5/N6.

## Root Cause

The previous execute attempt failed before any business row was written:

```text
ForeignKeyViolation:
stock_action_confirmation_projection_metric.source_snapshot_run_id
v3_realtime_virtual_metric_source_payload_20260612_no_snapshot_source
does not exist in common_market_data_run(run_id)
```

The writer had correctly made `source_snapshot_id` nullable, but it still filled
legacy required run-id columns with synthetic fallback run ids:

```text
source_snapshot_run_id = v3_realtime_virtual_metric_source_payload_20260612_no_snapshot_source
source_today_minute_run_id = v3_realtime_virtual_metric_source_payload_20260612_retained_today_1m
source_previous_day_minute_run_id = v3_realtime_virtual_metric_source_payload_20260611_retained_previous_day_1m
```

Those values are not rows in `common_market_data_run`, so the DB FK correctly
blocked the insert.

## Repair

The writer now uses reviewed source run-id lineage from the contract when it is
present:

```text
source_snapshot_run_id =
  realtime_daily_snapshot_20260612_standard_outbox_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1

source_today_minute_run_id =
  today_minute_bar_1m_20260612_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1

source_previous_day_minute_run_id =
  previous_day_minute_preload_20260611_for_20260612__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
```

`source_snapshot_run_id` is used as a reviewed standard snapshot outbox FK
anchor for a legacy schema column. The metric evidence remains minute-based and
traceable through `source_today_minute_run_id`,
`source_previous_day_minute_run_id`, `source_minute_refs`, and
`previous_day_minute_refs`.

The writer also blocks unresolved fallback lineage before DB write:

```text
source_run_id_fk_lineage_unresolved
```

## Materialized Proof

Plan-only materialization from the current contract and payload:

```text
rows stock/index/board/total = 62/0/38/100
B_BUY/S_SELL = 76/24
source_snapshot_run_id rows = 100
source_today_minute_run_id rows = 100
source_previous_day_minute_run_id rows = 100
lineage_policy = contract_reviewed_source_run_id_fk_lineage: 100
fallback source run-id prefix rows = 0
writer validation = valid=true
```

## Boundary

- writer executed: `false`
- database written: `false`
- rollback executed: `false`
- outbox/inbox/checkpoint consumed or updated: `false`
- N4/N5 executed: `false`
- N6 entered: `false`
- voice/mobile/sim/trade touched: `false`
- scheduler/worker started: `false`
- old system modified: `false`

## Next Gate

```text
V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_EXECUTE_FINAL_GATE_REVIEW_AFTER_SOURCE_RUN_ID_FK_REPAIR
```
