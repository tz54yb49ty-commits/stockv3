# N3-A1 After N2-Display Current Previous-Day Minute Execute Contract

## Summary

- result: `PREFLIGHT_PASS`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- source_condition_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- previous_day_minute_date: `20260522`
- expected_row_count: `525120`
- writes_outbox: `false`
- P0/P1/P2: `0/1/0`

## Metadata-Only Run Strategy

推荐：`方案 B：fill-facts/resume existing metadata-only run`。

方案 A 删除 metadata-only run 再用旧 runner 初次 execute，优点是复用旧 runner；缺点是会临时删除当前权威 preload run，且该 run 已被 B1 readiness / 总控引用，执行中断时风险更高。

方案 B 保留当前 run_id，只新增 fill-facts/resume 模式，在同一 current preload_run_id 下补 minute facts/status/quality。它能让 B2 trace 正式指向 current lineage，且 rollback 可回到 metadata-only 状态。

## Current Metadata State

- run status: `passed`
- market_data_pulled: `False`
- market_data_fact_written: `False`
- current minute fact rows: `0`
- current preload_status rows: `2188`
- current quality rows: `9`
- current preload outbox rows: `0`
- global outbox rows observed, not blocking: `55492`

## Expected Asset Counts

- stock: objects=`2052` subscriptions=`2052` expected_rows=`492480`
- index: objects=`9` subscriptions=`9` expected_rows=`2160`
- board: objects=`127` subscriptions=`127` expected_rows=`30480`

## Allowed Writes

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_minute_bar_1m`
- `index_minute_bar_1m`
- `board_minute_bar_1m`
- `stock_previous_day_minute_preload_status`
- `index_previous_day_minute_preload_status`
- `board_previous_day_minute_preload_status`

## Forbidden

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`
- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `trigger`
- `action`
- `user`
- `voice`
- `mobile`
- `sim`
- `position`

## Outbox Policy

- Only check `common_event_outbox WHERE source_run_id = preload_run_id`.
- Do not require global outbox to be empty; N3-B1 pending `MarketSnapshotUpdated=2188` is normal.

## Runner Requirement

- Existing A1 runner cannot directly execute this contract because it blocks when `preload_run_id` already exists.
- Add a fill-facts/resume runner or modify runner behind an explicit mode.
- Fill runner quality rows must use `n3_a1_current_fill_` gate-code prefix so rollback can preserve existing `n3_a1_lineage_` metadata quality rows.
- This contract does not authorize execute until that implementation/preflight is reviewed.

## Rollback

- rollback_sql_path: `sql/N3_A1_AFTER_N2_DISPLAY_current_previous_day_minute_rollback.sql`
- rollback deletes current preload minute facts and only fill-specific quality rows (`gate_code LIKE 'n3_a1_current_fill_%'`); it preserves existing metadata-only lineage quality rows.
- rollback preserves metadata-only preload status rows and does not touch `common_event_outbox`.

## Quality

- P0 passed `n3_a1_current_source_subscription_passed` expected=`status=passed` actual=`passed`
- P0 passed `n3_a1_current_metadata_run_exists` expected=`status=passed` actual=`passed`
- P0 passed `n3_a1_current_run_metadata_only` expected=`market_data_pulled=false, market_data_fact_written=false, minute_fact_rows=0` actual=`market_data_pulled=False market_data_fact_written=False minute_rows=0`
- P0 passed `n3_a1_current_status_rows_present` expected=`2188` actual=`2188`
- P0 passed `n3_a1_current_preload_outbox_zero` expected=`0` actual=`0`
- P0 passed `n3_a1_current_preload_inbox_zero` expected=`0` actual=`0`
- P0 passed `n3_a1_asset_counts_from_current_subscription` expected=`stock=2052,index=9,board=127` actual=`{"stock": {"asset_kind": "stock", "subscription_count": 2052, "object_count": 2052, "min_data_trade_date": "20260522", "max_data_trade_date": "20260522"}, "index": {"asset_kind": "index", "subscription_count": 9, "object_count": 9, "min_data_trade_date": "20260522", "max_data_trade_date": "20260522"}, "board": {"asset_kind": "board", "subscription_count": 127, "object_count": 127, "min_data_trade_date": "20260522", "max_data_trade_date": "20260522"}}`
- P0 passed `n3_a1_pull_plan_covers_assets` expected=`stock,index,board` actual=`board,index,stock`
- P1 warning `n3_a1_bj_920xxx_missing_expected` expected=`9 visible missing objects` actual=`9 expected by old/current status evidence`

## Next Gate

- allow_implementation: `True`
- allow_execute_gate: `False`
- needs_total_control_review: `True`
