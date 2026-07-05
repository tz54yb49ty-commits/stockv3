# V3 20260616 N3 Corrected Metric Scope Expansion Contract

- result: `BLOCKED`
- target_run_id: `action_confirmation_projection_metric_20260616_until_1401_historical_replay_formal_amount_chain_scope_expansion_v1__trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v4`
- context_run_id: `trigger_context_snapshot_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- total_context_rows: `4684`

## Expanded Scope

- BUY: `1959`
- SELL: `2025`
- SELL_HINT: `574`
- BUY_HINT: `46`
- SELL:FULL: `7`
- BUY:FULL: `73`

## Source Coverage

- strict_v4_source_complete_context_rows: `1401/4684`
- old_hint_post_review_source_identity_context_rows: `1860/4684`
- missing_previous_day_v4_a1_objects: `{'stock': 1272, 'index': 66, 'board': 74, 'total': 1412}`
- missing_current_v4_closed_minute_objects: `{'stock': 1407, 'index': 70, 'board': 88, 'total': 1565}`

## Blockers

- `expanded_scope_strict_v4_source_coverage_incomplete`
- `buy_full_source_coverage_zero`
- `sell_full_source_coverage_zero`
- `previous_day_v4_a1_source_missing_for_expanded_scope`
- `current_v4_closed_minute_source_missing_for_expanded_scope`

## Formal Amount Chain Unit Proof

- unit_conversion_policy: `formal_amount_chain_thousand_yuan_to_yuan_v1`
- amount_unit: `yuan`
- amount_rule: `attachment_dwmqy_avg_chain`
- metric_policy: `previous_day_same_window_elapsed_ratio_v1`
- current_period_amount_source_kind: `N3_standard_period_metric`
- ordinary_full_proof_status: `BLOCKED_source_incomplete_before_runner_validation`
- hint_proof_status: `old_hint_metric_post_review_passed_for_620_rows; strict_v4_source_only_covers_467_hint_rows`

## Forbidden Scope

- database_written: `False`
- metric_executed: `False`
- n4_entered: `False`
- n5_entered: `False`
- n6_entered: `False`
- outbox_inbox_checkpoint_consumed_or_updated: `False`
- scheduler_or_worker_started: `False`
- voice_mobile_sim_position_order_real_trade_touched: `False`
- old_system_read_or_modified: `False`
