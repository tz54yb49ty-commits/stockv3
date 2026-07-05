# N3 C1 Full-Context Expansion Execute Preflight

- preflight_result: `PREFLIGHT_PASS`
- ready: `true`
- planned_source_market_data_run_id: `market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- planned_today_minute_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1`
- original_c1_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- for_trade_date: `20260603`
- latest_closed_minute: `2026-06-03T15:00:00+08:00`
- expected objects stock/index/board/total: `1722/81/394/2197`
- expected rows stock/index/board/total: `413280/19440/94560/527280`
- target baseline run/quality/stock/index/board/outbox/inbox/checkpoint: `0/0/0/0/0/0/0/0`
- duplicate risk with original C1: `none`
- P0/P1/P2: `0/0/0`
- rollback_sql: `sql/N3_C1_full_context_scope_expansion_20260603_rollback.sql`

## Boundary

- no execute in this gate
- market_data_pulled=false
- minute_bar_written=false
- event_outbox_written=false
- outbox_consumed=false
- downstream_layers_touched=false
- worker_started=false
