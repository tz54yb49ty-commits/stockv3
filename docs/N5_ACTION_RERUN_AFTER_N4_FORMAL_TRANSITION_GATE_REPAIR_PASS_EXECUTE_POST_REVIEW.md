# N5 Action Rerun After N4 Formal Transition Gate Repair PASS Execute Post Review

Result: `PASS`

- action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_formal_transition_gate_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_formal_transition_gate_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- consumed TriggerMatched: 302
- ignored TriggerPendingMarketData: 4024
- ignored TriggerStateChanged: 0
- row counts: `{'common_action_run': 1, 'common_action_quality_item': 0, 'stock_action_fact': 240, 'index_action_fact': 16, 'board_action_fact': 46, 'common_action_event': 302, 'common_event_outbox_n5': 302, 'common_event_inbox_n5_consumer': 302, 'common_event_consumer_checkpoint_scoped_payload_refs': 301}`
- action_state: `{'blocked': 290, 'executed': 12}`
- action events: `{'ActionBlocked': 290, 'ActionExecuted': 12}`
- final action_mark: `{'<null>': 290, '30m_shrink': 4, '30m_volume': 5, 'normal': 3}`
- runtime signal types: `{'B_BUY': 60, 'S_SELL': 242}`
- source trigger event type: `{'TriggerMatched': 302}`
- N5 outbox status: `{'ActionBlocked:pending': 290, 'ActionExecuted:pending': 12}`
- N4 outbox status after: `{'TriggerMatched:pending': 302, 'TriggerPendingMarketData:pending': 4024}`
- target non-entries: `{'stock:SZ:300687 BUY:Y,M,D': {'common_trigger_match': 0, 'common_action_event': 0, 'stock_action_fact': 0}, 'stock:SZ:300684 BUY:M,D': {'common_trigger_match': 0, 'common_action_event': 0, 'stock_action_fact': 0}}`
- rollback SQL: `sql/N5_action_rerun_after_n4_formal_transition_gate_repair_rollback.sql`

No N6, N5 outbox consumption, N4 outbox status update, worker, voice/mobile/sim/position/order/real trade, old-system access, or rollback SQL execution was performed.
