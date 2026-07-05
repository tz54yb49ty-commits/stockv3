# N3-B2 Realtime Projection Execute Contract

## Summary

- layer_role: `N3_market_data`
- execute_authorized: `false`
- projection_run_id: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- projection_run_id_rule: `realtime_projection_metric_{for_trade_date}__{snapshot_run_id}`
- source_condition_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- subscription_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- snapshot_run_id: `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- preload_run_id: `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- today_minute_run_id: `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`

## Expected Rows

- total projection rows: `2188`
- stock: `2052` = ready `2043` + not_ready `9`
- index: `9` = ready `9`
- board: `127` = not_ready `127`

## Ready / Not Ready Policy

- ready rows: `2052`; these are candidate N4 matcher inputs only after formal B2 execute and post-review.
- board rows stay not_ready: `127`, because B1 board snapshot_time=`15:00` while C1 latest_closed_minute=`14:11`.
- BJ 920xxx stock rows stay not_ready/warning: `9`, because A1/C1 minute facts are missing.

## Allowed Writes

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`

## Quality Data Domain Contract

- allowed `common_market_data_quality_item.data_domain`: `common`, `stock`, `index`, `board`
- forbidden `data_domain`: `market_data_projection`
- required `common_market_data_quality_item.layer_scope`: `market_data_run`
- forbidden `layer_scope`: `realtime_projection_metric`
- run-level / aggregate projection quality: `data_domain=common`
- stock projection quality: `data_domain=stock`, `table_name=stock_realtime_projection_metric`
- index projection quality: `data_domain=index`, `table_name=index_realtime_projection_metric`
- board projection quality: `data_domain=board`, `table_name=board_realtime_projection_metric`
- projection semantics must be carried by `table_name`, `gate_code`, and `details.metric_scope=realtime_projection_metric`
- every B2 projection quality item must include `details.projection_run_id`, `details.asset_kind`, and `details.projection_schema_version`

## Forbidden

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `MarketSnapshotUpdated.payload_json` update
- `stock/index/board_realtime_daily_snapshot`
- `stock/index/board_minute_bar_1m`
- condition / trigger / action / user / voice / mobile / sim / position tables
- worker startup

## Rollback

Rollback by `projection_run_id` using `sql/N3_B2_realtime_projection_rollback.sql`.
If N4 has consumed projection facts, rollback N4 trigger facts/outbox/inbox/checkpoint first, then rollback N3.
