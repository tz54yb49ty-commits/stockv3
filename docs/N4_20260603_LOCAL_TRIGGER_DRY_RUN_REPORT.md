# N4 20260528 Local Trigger Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- stage: N4-20260603-local-trigger-dry-run
- layer_role: N4_trigger
- trigger_context_run_id: trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1
- snapshot_run_id: realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
- source_condition_run_id: condition_layer_20260602_source_20260602_v1
- for_trade_date: 20260603
- context_candidate_count: 5222
- candidate_count: 10167
- matched_plan_count: 1252
- pending_plan_count: 8915
- state_change_plan_count: 10167
- P0/P1/P2: 0/2/0

## Distribution

- by_asset_kind: {'board': 1746, 'index': 334, 'stock': 8087}
- matched_by_asset_kind: {'board': 170, 'index': 26, 'stock': 1056}
- pending_by_asset_kind: {'board': 1576, 'index': 308, 'stock': 7031}
- by_direction: {'buy': 5164, 'sell': 5003}
- by_signal_type: {'B_BUY': 5164, 'S_SELL': 5003}
- matched_by_signal_type: {'B_BUY': 1056, 'S_SELL': 196}
- pending_by_signal_type: {'B_BUY': 4108, 'S_SELL': 4807}
- by_trigger_mark_candidate: {'30m_shrink': 2471, '30m_volume': 2474, 'normal': 5222}
- matched_by_trigger_mark_candidate: {'normal': 1252}
- pending_by_trigger_mark_candidate: {'30m_shrink': 2471, '30m_volume': 2474, 'normal': 3970}
- by_legacy_signal_type: {'BUY_HINT': 216, 'B_BUY': 2474, 'B_BUY_30M_VOL': 2474, 'SELL_HINT': 61, 'S_SELL': 2471, 'S_SELL_30M_SHRINK': 2471}
- deprecated_runtime_signal_type_count: 0
- buy_hint_condition_key_trace_count: 216
- sell_hint_condition_key_trace_count: 61
- pending_market_data_trigger_live_false_count: 8915
- trigger_period_distribution: {'30m': 5222, 'D': 4031, 'M': 121, 'Q': 241, 'W': 462, 'Y': 90}
- planned_output_event_types: {'TriggerMatched': 1252, 'TriggerPendingMarketData': 8915, 'TriggerStateChanged': 10167}

## Input / Target Refs

- upstream_input_refs: {'upstream_input_outbox_allowed': 0, 'upstream_input_outbox_disallowed': 0, 'upstream_input_inbox_refs': 0, 'upstream_input_checkpoint_refs': 0}
- target_output_refs: {'target_output_outbox_refs': 0, 'target_inbox_refs': 0, 'target_checkpoint_refs': 0, 'target_trigger_match_refs': 0, 'target_trigger_state_refs': 0}
- scoped_event_refs: {'upstream_input_outbox_allowed': 0, 'upstream_input_outbox_disallowed': 0, 'upstream_input_inbox_refs': 0, 'upstream_input_checkpoint_refs': 0, 'target_output_outbox_refs': 0, 'target_inbox_refs': 0, 'target_checkpoint_refs': 0, 'target_trigger_match_refs': 0, 'target_trigger_state_refs': 0}

## Abnormal Rows

- missing_snapshot_context_rows: 0
- snapshot_quality_not_passed_plan_count: 0
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- projection_not_available_pending_plan_count: 5222

## Scoped Event Refs

- scoped_event_refs: {'upstream_input_outbox_allowed': 0, 'upstream_input_outbox_disallowed': 0, 'upstream_input_inbox_refs': 0, 'upstream_input_checkpoint_refs': 0, 'target_output_outbox_refs': 0, 'target_inbox_refs': 0, 'target_checkpoint_refs': 0, 'target_trigger_match_refs': 0, 'target_trigger_state_refs': 0}

## Quality

- P0 passed n4_20260528_context_run_ready: expected=trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1 actual=trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1
- P0 passed n4_20260528_snapshot_run_ready: expected=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1 actual=realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1
- P0 passed n4_20260528_context_rows_available: expected=>0 actual=5222
- P0 passed n4_20260528_snapshot_rows_available: expected=>0 actual=2474
- P0 passed n4_20260528_context_snapshot_coverage: expected=0 missing context objects actual=0
- P0 passed n4_20260528_period_trigger_baseline_json_present: expected=missing=0 actual=0
- P0 passed n4_20260528_required_period_baseline_ready: expected=required_period_not_ready_rows=0 actual=0
- P0 passed n4_20260528_plan_payload_traces_period_baseline: expected=10167 actual=10167
- P0 passed n4_20260528_snapshot_ordinary_candidate_plans: expected=>0 actual=1252
- P0 passed n4_20260528_projection_signal_candidates_visible: expected=>0 actual=5222
- P0 passed n4_20260528_canonical_payload_alignment: expected=canonical_payload_invalid_count=0 actual=0
- P0 passed n4_20260528_no_database_rows_written: expected=before row counts equal after row counts actual=unchanged
- P0 passed n4_local_dry_run_upstream_input_refs_compatible: expected=upstream disallowed/inbox/checkpoint refs=0 actual={"upstream_input_checkpoint_refs": 0, "upstream_input_inbox_refs": 0, "upstream_input_outbox_disallowed": 0}
- P0 passed n4_local_dry_run_upstream_input_outbox_allowlisted: expected=allowed upstream input outbox >= 0 actual=0
- P0 passed n4_local_dry_run_target_refs_zero: expected=target output/state/match/inbox/checkpoint refs=0 actual={"target_checkpoint_refs": 0, "target_inbox_refs": 0, "target_output_outbox_refs": 0, "target_trigger_match_refs": 0, "target_trigger_state_refs": 0}
- P1 warning n4_20260528_b1_p1_carried: expected=visible if present actual=1
- P1 warning n4_20260528_projection_candidates_pending: expected=pending candidates visible, no TriggerMatched write actual=5222
- P0 passed n4_20260528_no_outbox_consumption: expected=None actual=None
- P0 passed n4_20260528_no_trigger_fact_write: expected=None actual=None
- P0 passed n4_20260528_no_standard_outbox_write: expected=None actual=None
- P0 passed n4_20260528_no_worker: expected=None actual=None

## Boundary Confirmation

- read_only_database_checks: true
- writes_performed: false
- common_event_outbox_consumed: false
- common_event_inbox_written: false
- checkpoint_written: false
- trigger_state_written: false
- trigger_match_written: false
- event_outbox_written: false
- market_data_pulled: false
- downstream_layers_touched: false
- worker_started: false
- old_system_touched: false
- external_n2_runtime_path_accessed: false

## Rollback

- rollback_sql_path: sql/N4_20260603_local_trigger_dry_run_rollback.sql
- Dry-run writes no DB rows; rollback SQL is a scoped guard/no-op for DB state.

## Next Gate

- allow_local_trigger_dry_run_review: true
- allow_trigger_execute: false
- allow_n5_action: false
- note: This is a local fact-only dry-run artifact; N5 remains blocked until a separately authorized N4 execute writes standard outbox.
