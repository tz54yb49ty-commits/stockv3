# V3 20260615 Full-Universe N3-N6 Replay Closeout

- result: `CLOSEOUT_PASS`
- full universe: `{'context_rows_by_asset': {'stock': 1894, 'index': 83, 'board': 127}, 'context_rows_total': 2104, 'objects_by_asset': {'stock': 1894, 'index': 83, 'board': 127}, 'objects_total': 2104, 'universe_source': 'V3_N2_minute_target_scope_and_N4_trigger_context_snapshot', 'old_system_read': False}`
- N3 metric rows: `{'rows': 454560, 'objects': 1894}/{'rows': 19440, 'objects': 81}/{'rows': 30480, 'objects': 127}`
- N4 outbox: `{'TriggerMatched': 3309, 'TriggerPendingMarketData': 28558, 'TriggerStateChanged': 19816}`
- N5 outbox: `{'ActionBlocked': 2996, 'ActionExecuted': 313}`
- N6 user projection/card/queue: `313/313/0`

## Coverage Exception

- policy: `quality_visible_no_fabricated_minute_rows`
- source_missing_objects: `index:BJ:899050`, `index:BJ:899601`
- source_missing_count: `2`
- metric_rows_materialized: `504480`
- N4 behavior: `TriggerPendingMarketData / no fabricated TriggerMatched`

## Boundary

- target_machine_old_system_read: `false`
- scheduler_worker_started: `false`
- voice_mobile_sim_position_order_real_trade_touched: `false`
