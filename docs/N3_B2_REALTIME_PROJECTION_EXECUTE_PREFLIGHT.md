# N3-B2 Realtime Projection Execute Preflight

## Summary

- result: `PREFLIGHT_PASS`
- projection_run_id: `realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- P0/P1/P2: `0/2/0`
- runner_readiness: `ready`
- next_allowed_step: `B2 execute final gate`
- generated_at: `2026-05-25T22:20:19+08:00`
- refresh_reason: `after B2 projection quality layer_scope contract fix`

## Lineage

- `subscription` `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute` passed_and_matched=`true`
- `snapshot` `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute` passed_and_matched=`true`
- `preload` `previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute` passed_and_matched=`true`
- `today_minute` `today_minute_bar_1m_20260525_until_1411__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute` passed_and_matched=`true`

## Existing State

- projection_run_exists: `false`
- projection table row_count total: `{"board_realtime_projection_metric": 0, "index_realtime_projection_metric": 0, "stock_realtime_projection_metric": 0}`
- projection_run row_count: `{"board_realtime_projection_metric": 0, "index_realtime_projection_metric": 0, "stock_realtime_projection_metric": 0}`
- quality rows for projection_run_id: `0`
- outbox rows for projection_run_id: `0`
- inbox rows for projection_run_id: `0`
- B1 snapshot outbox status: `{"pending": 2188}`
- B1 snapshot inbox rows: `0`
- input inbox rows: `0`

## Dry-run Carry Forward

- expected projection rows: `{"board": 127, "index": 9, "stock": 2052, "total": 2188}`
- actual projection rows preview: `{"board": 127, "index": 9, "stock": 2052, "total": 2188}`
- ready_by_asset: `{"index": 9, "stock": 2043}`
- not_ready_by_asset: `{"board": 127, "stock": 9}`
- board_not_ready: `127`
- BJ 920xxx not_ready: `9`
- projection_signal_status: `{"down_volume_expanding": 96, "down_volume_flat": 79, "down_volume_shrinking": 174, "flat": 577, "unknown": 136, "up_volume_expanding": 305, "up_volume_flat": 342, "up_volume_shrinking": 479}`

## Quality Data Domain Policy

- allowed `common_market_data_quality_item.data_domain`: `common, stock, index, board`
- forbidden `data_domain`: `market_data_projection`
- required `common_market_data_quality_item.layer_scope`: `market_data_run`
- forbidden `layer_scope`: `realtime_projection_metric`
- preview quality domains: `["board", "common", "stock"]`
- preview table names: `["board_realtime_projection_metric", "stock/index/board_realtime_projection_metric", "stock_realtime_projection_metric"]`
- preview metric scopes: `["realtime_projection_metric"]`
- preview asset kinds: `["board", "common", "stock"]`
- preview quality item count: `6`
- database constraints: `data_domain IN (common, stock, index, board); layer_scope IN (active_condition_run, market_data_subscription_candidate, market_data_subscription_dedup, market_data_pull_plan, market_data_run)`
- projection semantics: `table_name`, `gate_code`, `details.metric_scope`, `details.projection_run_id`, `details.asset_kind`, `details.projection_schema_version`

## Runner Readiness

- existing runners: `["scripts/run_realtime_projection_metric_once.py", "src/ashare_v3/market/realtime_projection_execute.py"]`
- implementation_required: `false`
- targeted runner test: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_realtime_projection_execute.py' -> OK`
- CLI help: `available`

## Write Scope

- allowed write tables: `["common_market_data_run", "common_market_data_quality_item", "stock_realtime_projection_metric", "index_realtime_projection_metric", "board_realtime_projection_metric"]`
- writes_outbox: `false`
- updates_market_snapshot_payload: `false`
- consumes_outbox: `false`

## Rollback

- rollback_sql_path: `sql/N3_B2_realtime_projection_rollback.sql`
- scoped_by_projection_run_id: `true`
- deletes_common_event_outbox: `false`
- deletes_common_event_inbox: `false`

## Blockers

- none

## Boundary

- database_changed: `false`
- projection_fact_written: `false`
- quality_item_written: `false`
- outbox_written: `false`
- outbox_consumed: `false`
- market_snapshot_payload_modified: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Execute Gate

- execute_allowed_after_user_confirmation: `true`
- execute_authorized_now: `false`
- requires_explicit_user_confirmation: `true`
- candidate command: see JSON `execute_gate.candidate_execute_command`
