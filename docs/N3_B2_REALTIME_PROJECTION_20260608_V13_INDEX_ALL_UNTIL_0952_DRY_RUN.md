# N3 B2 Realtime Projection 20260608 v13 Index-All Until 09:52 Dry Run

- result: `DRY_RUN_PASS`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- generated_at_utc: `2026-06-08T02:17:45.336841+00:00`

## Rows

| key | value |
|---|---|
| stock | `1945` |
| index | `83` |
| board | `127` |
| total | `2155` |

## Distribution

| key | value |
|---|---|
| ready_rows | `359` |
| ready_by_asset | `{"index": 6, "stock": 353}` |
| not_ready_rows | `1796` |
| not_ready_by_asset | `{"board": 127, "index": 77, "stock": 1592}` |
| projection_signal_status | `{"down_volume_expanding": 40, "down_volume_flat": 20, "down_volume_shrinking": 4, "flat": 13, "unknown": 1796, "up_volume_expanding": 197, "up_volume_flat": 67, "up_volume_shrinking": 18}` |
| projection_quality_status | `{"blocked": 1796, "passed": 359}` |
| trace_status | `{"blocked": 1796, "passed": 359}` |
| board_not_ready | `127` |
| bj_920xxx_not_ready | `0` |

## Baseline

| key | value |
|---|---|
| projection_run_exists | `False` |
| projection_run_table_counts | `{"board_realtime_projection_metric": 0, "index_realtime_projection_metric": 0, "stock_realtime_projection_metric": 0}` |
| quality_rows_for_projection_run | `0` |
| outbox_rows_for_projection_run | `0` |
| inbox_rows_for_projection_run | `0` |
| checkpoint_refs_for_projection_run | `0` |
| snapshot_outbox_status | `{"pending": 2155}` |
| projection_table_counts_total_before | `{"board_realtime_projection_metric": 983, "index_realtime_projection_metric": 101, "stock_realtime_projection_metric": 5980}` |
| downstream_ref_baseline | `{"common_action_event": 0, "common_trigger_match": 0, "common_trigger_state": 0, "user_notification_queue": 0, "user_projection_run": 0, "user_signal_card": 0, "user_signal_projection": 0}` |

## Quality

| key | value |
|---|---|
| p0_count | `0` |
| p1_count | `3` |
| p2_count | `0` |

## Forbidden Scope Proof

| key | value |
|---|---|
| no_execute_in_runtime_control | `True` |
| no_market_data_pull | `True` |
| no_snapshot_or_minute_fact_write | `True` |
| no_outbox_write_or_consumption | `True` |
| no_inbox_or_checkpoint_update | `True` |
| no_worker | `True` |
| no_N4_N5_N6 | `True` |
| no_delivery_push_voice_mobile | `True` |
| no_sim_position_pnl_real_trade | `True` |
| no_proposal_order_trade | `True` |
