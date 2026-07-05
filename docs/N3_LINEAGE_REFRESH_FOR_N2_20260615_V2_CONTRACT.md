# N3 Lineage Refresh For N2 20260615 V2 Contract

Result: `CONTRACT_PASS`

## Staged Execute Contract

Stage 1 persists only N3 subscription control rows for `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`.
Stage 2 executes A1 previous-day preload for `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2` only after Stage 1 passes.

## Planned Writes

- Stage 1 common_market_data_run: `1`
- Stage 1 common_market_data_quality_item: `34`
- Stage 1 candidate/subscription/pull_plan: `5924/3272/9`
- Stage 2 expected minute rows stock/index/board/total: `132000/4080/12720/148800`
- Stage 2 status rows stock/index/board/total: `550/17/53/620`

## Allowed Write Tables

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`
- `stock_minute_bar_1m`
- `index_minute_bar_1m`
- `board_minute_bar_1m`
- `stock_previous_day_minute_preload_status`
- `index_previous_day_minute_preload_status`
- `board_previous_day_minute_preload_status`

## Forbidden Scope

- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`
- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `N4 tables`
- `N5 tables`
- `N6 tables`
- `voice/mobile/sim/position/order/real_trade`
- `old system`

## Rollback

- rollback_sql_path: `sql/N3_lineage_refresh_for_N2_20260615_v2_rollback.sql`
- hard_fail_before_delete_update: `true`
- preserves old v1 lineage: `true`
- no DROP/TRUNCATE/CASCADE: `true`

## Quality

- P0/P1/P2: `0/2/0`
