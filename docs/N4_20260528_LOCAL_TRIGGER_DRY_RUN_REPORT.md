# N4 20260528 Local Trigger Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- stage: N4-20260528-local-trigger-dry-run
- layer_role: N4_trigger
- trigger_context_run_id: trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v1
- snapshot_run_id: realtime_snapshot_20260528_retry1_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1
- source_condition_run_id: condition_layer_20260527_source_20260527_v1
- for_trade_date: 20260528
- context_candidate_count: 4602
- candidate_count: 8887
- matched_plan_count: 4285
- pending_plan_count: 4602
- P0/P1/P2: 0/2/0

## Distribution

- by_asset_kind: {'board': 527, 'index': 40, 'stock': 8320}
- matched_by_asset_kind: {'board': 254, 'index': 18, 'stock': 4013}
- pending_by_asset_kind: {'board': 273, 'index': 22, 'stock': 4307}
- by_direction: {'buy': 4576, 'sell': 4311}
- by_signal_type: {'BUY_HINT': 286, 'B_BUY': 4290, 'SELL_HINT': 31, 'S_SELL': 4280}
- matched_by_signal_type: {'B_BUY': 2145, 'S_SELL': 2140}
- pending_by_signal_type: {'BUY_HINT': 286, 'B_BUY': 2145, 'SELL_HINT': 31, 'S_SELL': 2140}
- by_action_mark: {'30m_shrink': 2140, '30m_volume': 2145, 'normal': 4602}
- matched_by_action_mark: {'normal': 4285}
- pending_by_action_mark: {'30m_shrink': 2140, '30m_volume': 2145, 'normal': 317}
- by_legacy_signal_type: {'BUY_HINT': 286, 'B_BUY': 2145, 'B_BUY_30M_VOL': 2145, 'SELL_HINT': 31, 'S_SELL': 2140, 'S_SELL_30M_SHRINK': 2140}
- trigger_period_distribution: {'30m': 4602, 'D': 3218, 'M': 369, 'Q': 80, 'W': 577, 'Y': 41}
- planned_output_event_types: {'TriggerMatched': 4285, 'TriggerPendingMarketData': 4602}

## Abnormal Rows

- missing_snapshot_context_rows: 0
- snapshot_quality_not_passed_plan_count: 0
- period_trigger_baseline_json_missing: 0
- required_period_not_ready_rows: 0
- projection_not_available_pending_plan_count: 4602

## Scoped Event Refs

- scoped_event_refs: {'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0, 'common_trigger_match': 0, 'common_trigger_state': 0}

## Quality

- P0 passed n4_20260528_context_run_ready: expected=trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v1 actual=trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v1
- P0 passed n4_20260528_snapshot_run_ready: expected=realtime_snapshot_20260528_retry1_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1 actual=realtime_snapshot_20260528_retry1_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1
- P0 passed n4_20260528_context_rows_available: expected=>0 actual=4602
- P0 passed n4_20260528_snapshot_rows_available: expected=>0 actual=2146
- P0 passed n4_20260528_context_snapshot_coverage: expected=0 missing context objects actual=0
- P0 passed n4_20260528_period_trigger_baseline_json_present: expected=missing=0 actual=0
- P0 passed n4_20260528_required_period_baseline_ready: expected=required_period_not_ready_rows=0 actual=0
- P0 passed n4_20260528_plan_payload_traces_period_baseline: expected=8887 actual=8887
- P0 passed n4_20260528_snapshot_ordinary_candidate_plans: expected=>0 actual=4285
- P0 passed n4_20260528_projection_signal_candidates_visible: expected=>0 actual=4602
- P0 passed n4_20260528_canonical_payload_alignment: expected=canonical_payload_invalid_count=0 actual=0
- P0 passed n4_20260528_no_database_rows_written: expected=before row counts equal after row counts actual=unchanged
- P0 passed n4_20260528_scoped_event_refs_zero: expected=all scoped refs=0 actual={"common_event_consumer_checkpoint": 0, "common_event_inbox": 0, "common_event_outbox": 0, "common_trigger_match": 0, "common_trigger_state": 0}
- P1 warning n4_20260528_b1_p1_carried: expected=visible if present actual=1
- P1 warning n4_20260528_projection_candidates_pending: expected=pending candidates visible, no TriggerMatched write actual=4602
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

- rollback_sql_path: sql/N4_20260528_local_trigger_dry_run_rollback.sql
- Dry-run writes no DB rows; rollback SQL is a scoped guard/no-op for DB state.

## Next Gate

- allow_local_trigger_dry_run_review: true
- allow_trigger_execute: false
- allow_n5_action: false
- note: This is a local fact-only dry-run artifact; N5 remains blocked until a separately authorized N4 execute writes standard outbox.
