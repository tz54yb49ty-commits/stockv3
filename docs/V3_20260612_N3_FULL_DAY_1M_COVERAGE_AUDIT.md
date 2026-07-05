# V3 20260612 N3 Full-Day 1m Coverage Audit

- result: `BLOCKED`
- blockers: `n3_1m_source_missing_for_context_scope, n3_metric_missing_for_context_scope`
- for_trade_date: `20260612`
- source_condition_run_id: `condition_layer_20260611_source_20260611_for_20260612_v1`
- trigger_context_run_id: `trigger_context_snapshot_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`

## Coverage

- missing minute objects: `1785`
- missing metric objects: `2038`
- missing minute sample: `['board:TDX:881002', 'board:TDX:881005', 'board:TDX:881007', 'board:TDX:881008', 'board:TDX:881016', 'board:TDX:881019', 'board:TDX:881026', 'board:TDX:881034', 'board:TDX:881051', 'board:TDX:881055', 'board:TDX:881062', 'board:TDX:881065', 'board:TDX:881075', 'board:TDX:881078', 'board:TDX:881082', 'board:TDX:881087', 'board:TDX:881091', 'board:TDX:881094', 'board:TDX:881097', 'board:TDX:881104']`
- missing metric sample: `['board:TDX:881005', 'board:TDX:881007', 'board:TDX:881008', 'board:TDX:881011', 'board:TDX:881016', 'board:TDX:881019', 'board:TDX:881026', 'board:TDX:881034', 'board:TDX:881044', 'board:TDX:881051', 'board:TDX:881055', 'board:TDX:881062', 'board:TDX:881065', 'board:TDX:881069', 'board:TDX:881071', 'board:TDX:881075', 'board:TDX:881078', 'board:TDX:881082', 'board:TDX:881091', 'board:TDX:881094']`

## 603259 Focus

- identity_key: `stock:SH:603259`
- focus minute: `10:56`
- scope/context rows: `2/2`
- minute/metric rows: `0/0`
- rows before focus: `0`

## Boundary

- old_system_read: `False`
- database_written: `False`
- outbox_inbox_checkpoint_consumed_or_updated: `False`
- n4_executed: `False`
- n5_executed: `False`
- n6_voice_mobile_sim_trade_touched: `False`
- scheduler_or_worker_started: `False`
