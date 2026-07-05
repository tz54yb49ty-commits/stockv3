# V3 20260615 N5 Replay After N4 Repaired Formal Price Amount Chain And N3 Coverage Repair Post Review

Result: `EXECUTE_PASS`

## Run

- source_trigger_run_id: `n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1`
- action_run_id: `v3_n5_action_replay_20260615_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_v1`
- consumer_name: `n5_action_consumer_v1`

## Row Count Proof

- expected: `{'common_action_run': 1, 'common_action_quality_item': 3696, 'stock_action_fact': 910, 'index_action_fact': 51, 'board_action_fact': 68, 'common_action_event': 1029, 'common_event_outbox': 1029, 'common_event_inbox': 4725, 'common_event_consumer_checkpoint': 2104}`
- actual: `{'common_action_run': 1, 'common_action_quality_item': 3696, 'stock_action_fact': 910, 'index_action_fact': 51, 'board_action_fact': 68, 'common_action_event': 1029, 'common_event_outbox': 1029, 'common_event_inbox': 4725, 'common_event_consumer_checkpoint': 2104}`
- row_count_match: `True`

## Event Distribution

- events: `{'ActionBlocked': 961, 'ActionExecuted': 68, 'ActionEligible': 0, 'ActionSkipped': 0}`
- n5_outbox: `[{'event_type': 'ActionBlocked', 'status': 'pending', 'c': 961}, {'event_type': 'ActionExecuted', 'status': 'pending', 'c': 68}]`

## Metric Join Proof

- total: `{'matched_rows': 1029, 'joined_metric_rows': 1029, 'missing_metric_rows': 0}`
- by_asset_kind: `{'stock': {'matched_rows': 910, 'joined_metric_rows': 910, 'missing_metric_rows': 0}, 'index': {'matched_rows': 51, 'joined_metric_rows': 51, 'missing_metric_rows': 0}, 'board': {'matched_rows': 68, 'joined_metric_rows': 68, 'missing_metric_rows': 0}}`

## Boundary Proof

- N4 outbox unchanged: `True` `[{'event_type': 'TriggerMatched', 'status': 'pending', 'c': 1029}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'c': 3696}]`
- downstream_refs: `{'user_projection_run': 0, 'user_signal_projection': 0, 'user_signal_card': 0, 'user_notification_queue': 0, 'position_state_refs': 0, 'position_event_refs': 0}`
- rollback_safe: `True`
- rollback_sql: `sql/V3_20260615_n5_replay_after_n4_repaired_formal_price_amount_chain_and_n3_coverage_repair_rollback.sql`

## Next

Return to runtime_control for N5 post-review registration. Do not enter N6 or consume N5 outbox in this gate.
