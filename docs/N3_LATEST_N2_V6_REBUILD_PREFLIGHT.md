# N3 Latest N2 v6 Rebuild Preflight

- result: `PREFLIGHT_PASS_WITH_NEW_RUN_ID`
- source_condition_run_id: `condition_layer_20260529_source_20260529_v6`
- dry_run_passed: `True`
- existing default run_id conflict: `True`
- recommended subscription run_id: `market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1`
- recommended A1 preload run_id: `previous_day_minute_preload_20260529_for_20260601__market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6_rebuild_20260602_v1`
- new baseline zero: `True`
- rollback_sql: `sql/N3_subscription_20260601_v6_rebuild_20260602_rollback.sql`
- rollback_registry: `docs/N3_subscription_20260601_v6_rebuild_20260602_rollback_registry.json`

## Expected Rows

```text
source_scope_rows=5216
source_scope_rows_by_asset_kind={'stock': 4087, 'index': 187, 'board': 942}
candidate_rows=6162
subscription_rows=3319
subscription_object_count=2373
object_count_by_asset_kind={'stock': 1862, 'index': 83, 'board': 428}
required_data_kind_counts={'minute_bar_1m': 473, 'previous_day_minute_bar_1m': 473, 'realtime_daily_snapshot': 2373}
previous_day_minute_required_count=473
previous_day_minute_required_count_by_asset_kind={'stock': 366, 'index': 21, 'board': 86}
previous_day_minute_date_counts={'20260529': 473}
pull_plan_rows=9
P0/P1/P2={'p0': 0, 'p1': 0, 'p2': 0}
```

## Boundary

Read-only preflight only. No execute, no DB write, no rollback, no outbox consume/update, no N4/N5/N6, no worker, no push/voice/mobile/sim/position/real trade.
