# V3 20260612 N4 HINT Basis Aligned N5 Replay Closeout

- result: `CLOSEOUT_PASS`
- generated_at: `2026-06-13T12:07:36.952599+08:00`
- N3 projection run: `action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1`
- N4 trigger run: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- N5 action run: `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`

## Decision

N4 HINT 30m basis alignment is now applied to the 20260612 fact chain. Old N4/N5 rows were scoped-rolled back first, then N4 was replayed with `current_30m_virtual_amount` vs `previous_day_same_window_amount`, and N5 was replayed from the refreshed N4 standard outbox.

## Row Proof

- N3 metric rows: stock/index/board = `62/0/38`; previous_day_same_window coverage = `62/0/38`
- N4 run status: `passed`; state/match-table/outbox = `4454/4454/4454`
- N4 outbox: `[{'event_type': 'TriggerMatched', 'status': 'pending', 'rows': 5}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'rows': 4449}]`
- N5 run status: `passed`; stock/index/board action facts = `3/0/2`
- N5 action events: `[{'event_type': 'ActionExecuted', 'rows': 5}]`
- N5 action_mark: `[{'action_mark': '30m_volume', 'rows': 5}]`
- N5 signal_type: `[{'signal_type': 'B_BUY', 'rows': 5}]`

## Boundary

- N4 outbox pending/delivered/delivering: `4454/0/0`
- N5 outbox pending/delivered/delivering: `5/0/0`
- N5 inbox/checkpoint for N4 source: `4454/2082`
- Downstream forbidden refs: `{'user_projection_run': 0, 'user_card_projection': 'table_absent', 'user_signal_projection': 0, 'user_signal_decision': 0, 'user_notification_queue': 0, 'user_notification_projection': 'table_absent', 'user_voice_delivery': 'table_absent', 'user_device_ack': 'table_absent', 'voice_delivery_queue': 'table_absent', 'mobile_projection': 'table_absent', 'mobile_notification_queue': 'table_absent', 'sim_projection': 'table_absent', 'sim_order': 'table_absent', 'sim_trade': 'table_absent', 'user_sim_order': 0, 'user_sim_trade': 0, 'user_sim_position': 0, 'common_position_state': 0, 'common_position_event': 0}`
- Scheduler/process proof: `{'scheduler': {'com.ashare-v3.v3-realtime-engine': {'returncode': 113, 'not_loaded': True, 'first_line': ['Bad request.', 'Could not find service "com.ashare-v3.v3-realtime-engine" in domain for user gui: 501']}, 'com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll': {'returncode': 113, 'not_loaded': True, 'first_line': ['Bad request.', 'Could not find service "com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll" in domain for user gui: 501']}, 'com.ashare-v3.n4.bounded-polling': {'returncode': 113, 'not_loaded': True, 'first_line': ['Bad request.', 'Could not find service "com.ashare-v3.n4.bounded-polling" in domain for user gui: 501']}}, 'process': {'returncode': 1, 'matches': []}}`

## Rollback Registry

- N4 rollback: `sql/V3_20260612_n4_hint_basis_aligned_replay_rollback.sql`; static proof: `{'path': 'sql/V3_20260612_n4_hint_basis_aligned_replay_rollback.sql', 'exists': True, 'do_guard_before_first_mutation': True, 'raise_exception_present_before_first_mutation': True, 'first_mutation_index': 1407, 'do_guard_index': 13, 'raise_exception_index': 356, 'contains_drop': False, 'contains_truncate': False, 'contains_cascade': False}`
- N5 rollback: `sql/V3_20260612_n5_hint_basis_aligned_replay_rollback.sql`; static proof: `{'path': 'sql/V3_20260612_n5_hint_basis_aligned_replay_rollback.sql', 'exists': True, 'do_guard_before_first_mutation': True, 'raise_exception_present_before_first_mutation': True, 'first_mutation_index': 5268, 'do_guard_index': 482, 'raise_exception_index': 1013, 'contains_drop': False, 'contains_truncate': False, 'contains_cascade': False}`

## Artifacts

- N4 dry-run: `docs/V3_20260612_N4_HINT_BASIS_ALIGNED_REPLAY_DRY_RUN.json`
- N4 execute: `docs/V3_20260612_N4_HINT_BASIS_ALIGNED_REPLAY_BUSINESS_EXECUTE_REPORT.json`
- N5 dry-run: `docs/V3_20260612_N5_HINT_BASIS_ALIGNED_REPLAY_DRY_RUN.json`
- N5 execute: `docs/V3_20260612_N5_HINT_BASIS_ALIGNED_REPLAY_EXECUTE_REPORT.json`

## Residual Notes

- N4 `common_trigger_match` contains outcome rows for matched and pending; canonical N5 entry remains N4 outbox `TriggerMatched=5`.
- `TriggerPendingMarketData=4449` produced N5 quality rows only and no action facts.
- N5 outbox remains pending and unconsumed; N6/user/voice/mobile/sim/position/order/real trade remain untouched.
