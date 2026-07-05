# V3 20260612 N5 Action Replay Baseline After N4 State Machine v3

- result: `BASELINE_PASS`
- source_trigger_run_id: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3`
- action_run_id: `v3_n5_action_replay_20260612_after_n4_state_machine_v3`
- consumer_name: `v3_n5_action_replay_20260612_state_machine_consumer_v3`
- n3_action_metric_run_id: `v3_n3_action_confirmation_metric_20260612_full_day_replay_v1`
- source_event_types: `TriggerMatched` only
- expected_read_event_count: `25282`
- entry_policy: TriggerPendingMarketData / TriggerStateChanged are non-entry events
- forbidden scope: no N6, no voice/mobile/sim/trade, no N4 outbox status update
