# V3 20260612 N4 Full-Day Trigger Replay Contract

- result: `CONTRACT_PASS`
- execute_run_id: `v3_n4_trigger_replay_20260615_attachment_rule_canonical_v1`
- expected_writes: `{'common_trigger_run': 1, 'common_trigger_quality_item': 'quality_items', 'common_trigger_state': 4564, 'common_trigger_match': 5853, 'common_event_outbox': 128450, 'TriggerMatched': 5853, 'TriggerPendingMarketData': 25308, 'TriggerStateChanged': 97289}`
- write_policy: `state-machine output: TriggerMatched action-entry; TriggerPendingMarketData/TriggerStateChanged non-entry`
- strict_guards: `{'ordinary_formal_30m_contamination': 0, 'formal_period_arrays_contains_30m': 0, 'ordinary_missing_formal_proof_trigger_matched': 0, 'known_polluted_sample_trigger_matched': 0, 'hint_30m_trigger_matched': 3007}`
