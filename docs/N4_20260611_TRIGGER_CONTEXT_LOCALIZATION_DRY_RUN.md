# N4 20260611 Trigger Context Localization Dry Run

Result: **DRY_RUN_PASS**

## Target
- trigger_context_run_id: `trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- source_condition_run_id: `condition_layer_20260610_source_20260610_for_20260611_v1`
- source_market_subscription_run_id: `market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`
- for_trade_date: `20260611`
- source_trade_date: `20260610`

## Context Row Plan
- stock/index/board/total: `4027/185/268/4480`
- object_count stock/index/board/total: `1890/83/127/2100`
- direction buy/sell: `2215/2265`
- condition_signal_distribution: `{'BUY': 2067, 'BUY:FULL': 33, 'BUY_HINT': 115, 'SELL': 2081, 'SELL:FULL': 16, 'SELL_HINT': 168}`
- hint rows BUY/SELL/total: `115/168/283`
- FULL rows total: `49`

## Quality
- P0/P1/P2: `0/0/0`
- period_trigger_baseline_json_missing: `0`
- trigger_baseline_semantic_missing: `0`
- baseline_source_trade_date_mismatch: `0`
- legacy_previous_used_as_trigger_baseline: `0`
- required_period_not_ready_rows: `0`

## Source Lineage Proof
- N2 run status: `passed_active`
- N3 subscription status: `passed` with rows/object/candidate = `2666/2100/5046`
- Latest B1 snapshot run: `realtime_daily_snapshot_20260611_until_1048__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`, facts stock/index/board/total = `1890/83/127/2100`, outbox rows = `0`
- Latest B2 projection run: `realtime_projection_metric_20260611_until_1048__realtime_daily_snapshot_20260611_until_1048__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1`, facts stock/index/board/total = `1890/83/127/2100`, outbox rows = `0`

## Boundary
No N4 execute, no DB write, no worker, no N3 outbox consumption/update, no N5/N6, no delivery/push/voice/mobile, no sim/position/pnl/real trade.

## Next
`N4_20260611_TRIGGER_CONTEXT_LOCALIZATION_EXECUTE_FINAL_GATE_REVIEW`
