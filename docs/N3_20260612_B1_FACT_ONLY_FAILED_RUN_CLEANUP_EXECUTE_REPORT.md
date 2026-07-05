# N3 20260612 B1 Fact-Only Failed Run Cleanup Execute Report

- Result: EXECUTE_PASS
- Generated at: 2026-06-12T10:52:31+08:00
- Cleanup SQL: `sql/N3_20260612_B1_fact_only_failed_runs_cleanup.sql`
- Command guard: `SET LOCAL ashare_v3.allow_n3_b1_20260612_failed_cleanup = 'true'` in the same transaction

## Target Runs

- `realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- `realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- `realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- `realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`

## Deleted Rows

- stock_realtime_daily_snapshot: 6897
- index_realtime_daily_snapshot: 8
- board_realtime_daily_snapshot: 0
- common_market_data_quality_item: 865
- common_market_data_run: 4

## Post-Cleanup Baseline

- target common_market_data_run: 0
- target quality rows: 0
- target stock/index/board snapshot rows: 0/0/0
- outbox/inbox/checkpoint refs: 0/0/0
- N3-B2/N4/N5/N6 refs: 0

## Boundary

No scheduler/wrapper/B1/C1/B2 runner was started. No outbox/inbox/checkpoint consumption or update was performed. No N4/N5/N6, voice/mobile/sim/trade path was entered.
