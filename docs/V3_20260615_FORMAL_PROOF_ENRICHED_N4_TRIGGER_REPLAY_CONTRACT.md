# V3 20260612 N4 Full-Day Trigger Replay Contract

- result: `CONTRACT_PASS`
- execute_run_id: `v3_n4_trigger_replay_20260615_after_formal_proof_enrichment_v1`
- expected_writes: `{'common_trigger_run': 1, 'common_trigger_quality_item': 'quality_items', 'common_trigger_state': 4513, 'common_trigger_match': 20472, 'common_event_outbox': 106211, 'TriggerMatched': 20472, 'TriggerPendingMarketData': 4, 'TriggerStateChanged': 85735}`
- write_policy: `state-machine output: TriggerMatched action-entry; TriggerPendingMarketData/TriggerStateChanged non-entry`
- strict_guards: `{'ordinary_formal_30m_contamination': 0, 'formal_period_arrays_contains_30m': 0, 'ordinary_missing_formal_proof_trigger_matched': 0, 'known_polluted_sample_trigger_matched': 9, 'hint_30m_trigger_matched': 3309}`
