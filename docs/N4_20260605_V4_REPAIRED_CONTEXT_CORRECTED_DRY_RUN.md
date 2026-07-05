# N4 20260605 V4 Repaired Context Corrected Dry-Run

- result: DRY_RUN_PASS
- stage: N4_REPAIRED_CONTEXT_CORRECTED_DRY_RUN_GATE
- generated_at: 2026-06-05T14:31:04.275286+00:00
- execute_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
- context_run_id: trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
- snapshot_run_id: realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1
- projection_run_id: realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1

## Counts

- candidate_count: 896
- compliant_count: 605
- blocked_count: 291
- P0/P1/P2: 0/1/0

## Blocked Reasons

- missing trigger_price: 275
- missing triggered_periods: 275
- FULL forbidden: 23
- invalid N5 entry: 0
- future event_time: 0
- future trigger_time: 0

## Semantic Delta Vs Tainted Run

- tainted_candidate_count: 1537
- repaired_candidate_count: 896
- candidate_delta: -641
- tainted_compliant_count: 1240
- repaired_compliant_count: 605
- compliant_delta: -635
- interpretation: counts changed because ordinary BUY/SELL matcher now consumes repaired trigger_previous_entity_high/low and trigger_previous_amount_baseline

## Matcher Proof

- ordinary_buy_uses: ['trigger_previous_entity_high', 'trigger_previous_amount_baseline']
- ordinary_sell_uses: ['trigger_previous_entity_low', 'trigger_previous_amount_baseline']
- trace_baseline_source_distribution_for_compliant: {'trigger_baseline': 605}
- all_compliant_trace_baseline_source_trigger_baseline: True

## Sample Proof

### stock:SZ:002399
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'BUY:Y,Q,M,W,D', 'signal_type': 'B_BUY', 'trigger_period': 'D', 'pending_reason': 'ordinary_snapshot_trigger_condition_not_met', 'dry_run_reason': 'BUY ordinary trigger requires current_price/close > trigger_previous_entity_high', 'trigger_price': '9.66', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '9.66', 'trigger_previous_entity_low': '9.45', 'trigger_previous_amount_baseline': '43678.117', 'previous_entity_high': '9.79', 'previous_entity_low': '9.67', 'previous_amount': '57061.027', 'previous_avg_amount': '57061.027', 'baseline_source_trade_date': '20260604'}}
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'BUY:Y,Q,M,W,D', 'signal_type': 'B_BUY', 'trigger_period': '30m', 'pending_reason': 'projection_fact_not_available_in_local_snapshot_dry_run', 'dry_run_reason': 'B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT require N3 standardized realtime projection or closed confirmation; local B1 fact-only snapshot is trace input only', 'trigger_price': '9.66', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '9.66', 'trigger_previous_entity_low': '9.45', 'trigger_previous_amount_baseline': '43678.117', 'previous_entity_high': '9.79', 'previous_entity_low': '9.67', 'previous_amount': '57061.027', 'previous_avg_amount': '57061.027', 'baseline_source_trade_date': '20260604'}}
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'SELL:M,W', 'signal_type': 'S_SELL', 'trigger_period': 'W', 'pending_reason': 'ordinary_snapshot_trigger_condition_not_met', 'dry_run_reason': 'SELL ordinary trigger requires current_price/close < open; snapshot body is not falling', 'trigger_price': '9.66', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '9.94', 'trigger_previous_entity_low': '9.45', 'trigger_previous_amount_baseline': '50350.426325', 'previous_entity_high': '10.18', 'previous_entity_low': '9.94', 'previous_amount': '39149.508884', 'previous_avg_amount': '39149.508884', 'baseline_source_trade_date': '20260604'}}

### index:SZ:399006
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'BUY:W,D', 'signal_type': 'B_BUY', 'trigger_period': 'D', 'pending_reason': 'ordinary_snapshot_trigger_condition_not_met', 'dry_run_reason': 'BUY ordinary trigger requires current_price/close > open; snapshot body is not rising', 'trigger_price': '4071.29', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '4088.88', 'trigger_previous_entity_low': '4072.55', 'trigger_previous_amount_baseline': '703241125888', 'previous_entity_high': '4122.99', 'previous_entity_low': '4089.02', 'previous_amount': '809214410752', 'previous_avg_amount': '809214410752', 'baseline_source_trade_date': '20260604'}}
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'BUY:W,D', 'signal_type': 'B_BUY', 'trigger_period': '30m', 'pending_reason': 'projection_fact_not_available_in_local_snapshot_dry_run', 'dry_run_reason': 'B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT require N3 standardized realtime projection or closed confirmation; local B1 fact-only snapshot is trace input only', 'trigger_price': '4071.29', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '4088.88', 'trigger_previous_entity_low': '4072.55', 'trigger_previous_amount_baseline': '703241125888', 'previous_entity_high': '4122.99', 'previous_entity_low': '4089.02', 'previous_amount': '809214410752', 'previous_avg_amount': '809214410752', 'baseline_source_trade_date': '20260604'}}
- {'output_event_type': 'TriggerPendingMarketData', 'plan_status': 'pending', 'condition_key': 'SELL:Y,Q,M,W', 'signal_type': 'S_SELL', 'trigger_period': 'W', 'pending_reason': 'ordinary_snapshot_trigger_condition_not_met', 'dry_run_reason': 'SELL ordinary trigger requires current_price/close < trigger_previous_entity_low', 'trigger_price': '4071.29', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '4088.88', 'trigger_previous_entity_low': '4057.39', 'trigger_previous_amount_baseline': '741739839488', 'previous_entity_high': '4037.95', 'previous_entity_low': '3974.97', 'previous_amount': '839011309977.6', 'previous_avg_amount': '839011309977.6', 'baseline_source_trade_date': '20260604'}}

### board_sample
- {'identity_key': 'board:TDX:880202', 'condition_key': 'SELL:Y', 'signal_type': 'S_SELL', 'output_event_type': 'TriggerMatched', 'trigger_period': 'Y', 'trigger_price': '1017.35', 'match_basis': 'realtime_snapshot', 'trace': {'baseline_source': 'trigger_baseline', 'trigger_previous_entity_high': '1075.79', 'trigger_previous_entity_low': '1019.65', 'trigger_previous_amount_baseline': '34071534487.51020408', 'previous_entity_high': '1063.52', 'previous_entity_low': '854.54', 'previous_amount': '16312731034.86419753', 'previous_avg_amount': '16312731034.86419753', 'baseline_source_trade_date': '20260604'}}

## N5 Eligibility Proof

- {'rule': 'TriggerMatched + B_BUY/S_SELL + matched + trigger_live=true + n5_entry_allowed=true', 'eligible_count': 605, 'invalid_n5_entry_count': 0}

## Boundary Proof

- no_db_write_proof: {'before_target_refs': {'common_trigger_run': 0, 'common_trigger_quality_item': 0, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}, 'after_target_refs': {'common_trigger_run': 0, 'common_trigger_quality_item': 0, 'common_trigger_state': 0, 'common_trigger_match': 0, 'common_event_outbox': 0, 'common_event_inbox': 0, 'common_event_consumer_checkpoint': 0}, 'unchanged': True}
- trigger_price_source_proof: {'required': 'trigger_price must match reviewed N3 snapshot/projection price', 'compliant_checked': 605, 'blocked_trigger_price_source_missing': 275}
- time_boundary_proof: {'created_at_reference': '2026-06-05T14:31:04.275286+00:00', 'future_event_time_blocked': 0, 'future_trigger_time_blocked': 0}
- full_blocked_proof: {'full_forbidden_blocked_count': 23, 'full_trigger_matched_allowed': False}

## Next Gate

- execute_preflight_could_pass: True
- next_gate: N4_REPAIRED_CONTEXT_CORRECTED_EXECUTE_CONTRACT_GATE
