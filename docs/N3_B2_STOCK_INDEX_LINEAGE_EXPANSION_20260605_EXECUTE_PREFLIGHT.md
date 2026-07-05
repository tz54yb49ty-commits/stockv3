# N3 B2 Stock/Index Minute Lineage Expansion Execute Preflight

- preflight_result: PREFLIGHT_PASS
- ready: true
- blockers: none
- expansion_run_id: `market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- candidate/subscription/pull_plan: 6696/3350/4
- objects: stock=1668 index=7 board=0 total=1675
- P0/P1/P2: 0/2/0
- rollback_sql: `sql/N3_B2_stock_index_lineage_expansion_20260605_rollback.sql`

## Write Scope Alignment

Allowed control-row writes:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`

`common_market_data_subscription_candidate` is explicitly included because the runner persists subscription candidate control rows before deduped subscriptions and pull plans. It is not a market-data fact table.

Forbidden writes remain:

- `stock/index/board_minute_bar_1m`
- `stock/index/board_previous_day_minute_preload_status`
- `stock/index/board_realtime_daily_snapshot`
- `stock/index/board_realtime_projection_metric`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- N4/N5/N6
