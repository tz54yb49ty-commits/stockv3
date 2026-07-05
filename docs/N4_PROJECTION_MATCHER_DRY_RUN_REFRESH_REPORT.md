# N4 Projection Matcher Implementation Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N4_trigger
- trigger_context_run_id: trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- projection_run_id: realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- candidate_count: 4512
- matched_count: 488
- pending_count: 276
- not_matched_signal_count: 3748
- P0/P1/P2: 0/2/0

## Match Summary

- matched_by_signal_type: {'BUY_HINT': 6, 'B_BUY': 305, 'SELL_HINT': 3, 'S_SELL': 174}
- pending_by_signal_type: {'B_BUY': 136, 'SELL_HINT': 4, 'S_SELL': 136}
- matched_by_action_mark: {'30m_shrink': 177, '30m_volume': 311}
- pending_by_action_mark: {'30m_shrink': 136, '30m_volume': 136, 'normal': 4}
- by_legacy_signal_type: {'BUY_HINT': 71, 'B_BUY_30M_VOL': 2187, 'SELL_HINT': 69, 'S_SELL_30M_SHRINK': 2185}
- not_matched_by_projection_signal_status: {'down_volume_expanding': 201, 'down_volume_flat': 163, 'down_volume_shrinking': 183, 'flat': 1195, 'up_volume_expanding': 309, 'up_volume_flat': 708, 'up_volume_shrinking': 989}
- buy_hint_matched_count: 6
- sell_hint_matched_count: 3

## Not Ready Summary

- pending_by_not_ready_classification: {'blocked': 258, 'warning': 18}
- board_not_ready_object_count: 127
- bj_920xxx_not_ready_object_count: 9

## Boundary Confirmation

- read_only_database_checks: true
- common_event_outbox_consumed: false
- common_event_inbox_written: false
- checkpoint_written: false
- trigger_match_written: false
- trigger_state_written: false
- event_outbox_written: false
- market_data_pulled: false
- raw_market_tables_read: false
- worker_started: false
- downstream_layers_touched: false
- old_system_touched: false
- external_n2_runtime_path_accessed: false

## Quality

- P0 passed n4_projection_matcher_context_run_ready: expected=trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute actual=trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- P0 passed n4_projection_matcher_current_context_not_synthetic: expected=not denylisted actual=False
- P0 passed n4_projection_matcher_context_rows_available: expected=>0 actual=4512
- P0 passed n4_projection_matcher_projection_rows_available: expected=>0 actual=2188
- P0 passed n4_projection_matcher_ready_only_match: expected=0 matched not-ready rows actual=0
- P0 passed n4_projection_matcher_board_bj_not_ready_no_match: expected=0 matched not-ready board/BJ rows actual=0
- P0 passed n4_projection_matcher_hint_signals_supported: expected=hint signal support present actual=BUY_HINT=6 SELL_HINT=3
- P0 passed n4_projection_matcher_no_forbidden_read_tables: expected=no forbidden read table overlap actual=
- P0 passed n4_projection_matcher_no_database_writes: expected=before row counts equal after row counts actual=unchanged
- P0 passed n4_projection_matcher_canonical_payload: expected=canonical payload errors=0 actual=errors=0 legacy_signal_types=
- P0 passed n4_projection_matcher_no_outbox_consumption: expected=None actual=None
- P0 passed n4_projection_matcher_no_market_adapter: expected=None actual=None
- P1 warning n4_projection_matcher_board_not_ready_visible: expected=visible if present actual=127
- P1 warning n4_projection_matcher_bj_920xxx_not_ready_visible: expected=visible if present actual=9

## Next Gate

- allow_projection_matcher_dry_run_refresh: true
- allow_real_execute_preflight: false
- execute_preflight_blocker: requires refreshed dry-run, inbox/checkpoint/ack/rollback review, and user authorization

## Rollback

- this_dry_run: No DB rollback required; delete generated matcher report files if discarded.
- future_execute: Future N4 execute rollback must delete N4 inbox/checkpoint, trigger_state, trigger_match, quality, and outbox rows by execute run_id after downstream safety checks.
