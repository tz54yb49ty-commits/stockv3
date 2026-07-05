# N4 20260605 V4 Corrected Dry-Run

- result: DRY_RUN_PASS
- generated_at: 2026-06-05T07:52:34.723131+00:00
- execute_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- context_run_id: trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
- snapshot_run_id: realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
- projection_run_id: realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1

## Input Readiness

- context_run_status: passed
- context_row_count: 5118
- snapshot_run_status: passed
- snapshot_row_count: 2389
- projection_row_count: 2389
- local_trigger_matched_candidates: 1262
- projection_trigger_matched_candidates: 275

## Strict Guard Summary

- candidate_plans_before_strict_guard: 1537
- persisted_plans_after_strict_guard: 1240
- compliant_count: 1240
- blocked_count: 297
- P0/P1/P2: 0/1/0

## Blocked Counts By Reason

  - missing trigger_price: 275
  - missing trigger_kind: 0
  - missing triggered_periods: 275
  - missing n5_entry_allowed: 0
  - future event_time: 0
  - future trigger_time: 0
  - FULL forbidden: 29
  - invalid signal_type: 0
  - invalid N5 entry: 0

## Compliant Distribution

- by_signal_type: {'B_BUY': 1180, 'S_SELL': 60}
- by_trigger_mark_candidate: {'normal': 1240}
- by_match_basis: {'realtime_snapshot': 1240}

## Compliant TriggerMatched Sample

  - identity_key=stock:SH:600000, condition_key=BUY:Y,Q,M,W,D, signal_type=B_BUY, trigger_price=9.21, trigger_time=2026-06-05 11:06:16.177782+08:00, triggered_periods=['D']
  - identity_key=stock:SH:600004, condition_key=BUY:Y,Q,M,W,D, signal_type=B_BUY, trigger_price=8.1, trigger_time=2026-06-05 11:06:16.230741+08:00, triggered_periods=['D']
  - identity_key=stock:SH:600006, condition_key=BUY:Y,Q,M,W,D, signal_type=B_BUY, trigger_price=6.03, trigger_time=2026-06-05 11:06:16.273257+08:00, triggered_periods=['D']
  - identity_key=stock:SH:600007, condition_key=BUY:Y,M,W,D, signal_type=B_BUY, trigger_price=21.09, trigger_time=2026-06-05 11:06:16.314343+08:00, triggered_periods=['D']
  - identity_key=stock:SH:600009, condition_key=BUY:Y,Q,M,W,D, signal_type=B_BUY, trigger_price=23.63, trigger_time=2026-06-05 11:06:16.405442+08:00, triggered_periods=['D']

## Boundary Proof

- trigger_price_source_proof: {'required': 'trigger_price must match reviewed N3 snapshot/projection price', 'compliant_checked': 1240, 'blocked_trigger_price_source_missing': 275}
- time_boundary_proof: {'created_at_reference': '2026-06-05T07:52:34.723131+00:00', 'future_event_time_blocked': 0, 'future_trigger_time_blocked': 0}
- full_blocked_proof: {'full_forbidden_blocked_count': 29, 'full_trigger_matched_allowed': False}
- n5_entry_eligibility_proof: {'rule': 'TriggerMatched + B_BUY/S_SELL + matched + trigger_live=true + n5_entry_allowed=true', 'eligible_count': 1240, 'invalid_n5_entry_count': 0}
- no_db_write_proof: {'before_target_refs': {'common_trigger_run': 0, 'common_trigger_quality_item': 0, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}, 'after_target_refs': {'common_trigger_run': 0, 'common_trigger_quality_item': 0, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}, 'unchanged': True}

## Next Gate

- execute_preflight_could_pass: True
- next_gate: N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT_GATE
