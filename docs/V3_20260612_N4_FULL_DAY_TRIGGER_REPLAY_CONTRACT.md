# V3 20260612 N4 Full-Day Trigger Replay Contract

- result: `CONTRACT_PASS`
- execute_run_id: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3`
- expected_writes: `{'common_trigger_run': 1, 'common_trigger_quality_item': 'quality_items', 'common_trigger_state': 4101, 'common_trigger_match': 25282, 'common_event_outbox': 114561, 'TriggerMatched': 25282, 'TriggerPendingMarketData': 4, 'TriggerStateChanged': 89275}`
- write_policy: `state-machine output: TriggerMatched action-entry; TriggerPendingMarketData/TriggerStateChanged non-entry`
