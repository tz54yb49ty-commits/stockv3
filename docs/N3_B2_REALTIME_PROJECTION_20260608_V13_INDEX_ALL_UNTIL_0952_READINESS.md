# N3 B2 Realtime Projection 20260608 v13 Index-All Until 09:52 Readiness

- result: `READINESS_PASS`
- projection_run_id: `realtime_projection_metric_20260608_until_0952__realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`
- generated_at_utc: `2026-06-08T02:17:45.335726+00:00`

## Source Proof

| key | value |
|---|---|
| B1 | `{"outbox_pending": 2155, "rows": {"board": 127, "index": 83, "stock": 1945, "total": 2155}, "run_id": "realtime_daily_snapshot_20260608__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"}` |
| A1 | `{"minute_rows_total": 89280, "objects": 372, "run_id": "previous_day_minute_preload_20260605__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"}` |
| C1 | `{"latest_closed_minute": "2026-06-08T09:52:00+08:00", "minute_rows_total": 8184, "objects": 372, "run_id": "today_minute_bar_1m_20260608_until_0952__market_data_subscription_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute"}` |

## Expected Projection Rows

| key | value |
|---|---|
| stock | `1945` |
| index | `83` |
| board | `127` |
| total | `2155` |

## Expected Distribution

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

## Not Ready Reasons

| key | value |
|---|---|
| amount_projection_ratio_not_computable | `1796` |
| missing_current_lineage_previous_day_elapsed | `1783` |
| missing_current_lineage_previous_day_window | `1783` |
| missing_today_minute_elapsed | `1796` |
| price_direction_unknown | `1796` |
| snapshot_time_after_c1_latest_closed_minute | `127` |

## Forbidden Scope Proof

| key | value |
|---|---|
| no_db_write_in_this_gate | `True` |
| no_outbox_consumption | `True` |
| no_worker_started | `True` |
| no_N4_N5_N6 | `True` |

## Next Gate

`N3_B2_REALTIME_PROJECTION_20260608_V13_INDEX_ALL_EXECUTE_FINAL_GATE_REVIEW`
