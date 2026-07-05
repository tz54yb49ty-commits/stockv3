
# V3 20260616 Realtime Virtual Metric Writer Contract

- result: `CONTRACT_PASS`
- target_run_id: `action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- expected rows stock/index/board/total: `564/17/53/634`
- metric_ready/not_ready: `634/0`
- source_payload: `docs/V3_20260616_realtime_virtual_metric_writer_payload.json` available_now=true
- 30m/5m virtual amount policy: `previous_day_same_window_elapsed_ratio_v1`
- allowed write tables: `common_market_data_run`, `common_market_data_quality_item`, `stock/index/board_action_confirmation_projection_metric`
- forbidden: outbox/inbox/checkpoint, B1/C1/preload facts, N4/N5/N6, scheduler/worker, voice/mobile/sim/trade
- rollback_sql_path: `sql/V3_20260616_realtime_virtual_metric_writer_runner_rollback.sql`
