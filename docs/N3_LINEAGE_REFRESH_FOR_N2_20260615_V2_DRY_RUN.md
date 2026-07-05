# N3 Lineage Refresh For N2 20260615 V2 Dry Run

Result: `DRY_RUN_PASS`

## Lineage

- old_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- new_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v2`
- new_subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- new_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v2`
- source_trade_date: `20260615`
- for_trade_date: `20260616`

## Subscription Dry Run

- source_scope_rows stock/index/board/total: `4194/183/307/4684`
- candidate/subscription/pull_plan: `5924/3272/9`
- subscription_object_count: `2032`
- required_data_kind_counts: `{'minute_bar_1m': 620, 'previous_day_minute_bar_1m': 620, 'realtime_daily_snapshot': 2032}`

## A1 Preload Plan

- objects stock/index/board/total: `550/17/53/620`
- expected minute rows stock/index/board/total: `132000/4080/12720/148800`
- writes_outbox: `false`

## Quality

- P0/P1/P2: `0/2/0`
