# N3 B2 Realtime Projection 20260605 Live2 Preflight Refresh

Status: **PREFLIGHT_PASS**

- projection_run_id: `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- snapshot_run_id: `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source today-minute runs: `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`, `today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- source previous-day runs: `previous_day_minute_preload_20260604_for_20260605__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`, `previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1`
- expected rows stock/index/board/total: 1952/9/428/2389
- ready rows: 969 ({"stock": 969})
- not_ready rows: 1420 ({"board": 428, "index": 9, "stock": 983})
- P0/P1/P2: 0/4/0
- writes_outbox: false

Stock/index missing minute lineage is cleared by the expansion A1/C1 facts. Remaining stock/index not_ready rows are completion-ratio quality-visible rows. Board rows requiring 14:59 remain quality-visible not_ready.

Rollback: `sql/N3_B2_realtime_projection_20260605_live2_compat_rollback.sql` hard-fails before DELETE on outbox/inbox/checkpoint, N4/N5/N6 refs, downstream flags, and worker flags.
