# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
- user_projection_run_id: v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 1187
- by_event_type: {'ActionBlocked': 911, 'ActionExecuted': 276}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 276
- user_signal_card: 276
- user_notification_queue: 276
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 1187
- target_price_missing: 1187
- expected_return_pct_missing: 1187
- display_basis_missing: 1187
- board_context_missing: 1187

## Boundary

- writes_database: false
- n5_outbox_consumed: false
- updates_n5_outbox_status: false
- writes_user_projection_run: false
- writes_user_signal_projection: false
- writes_user_signal_card: false
- writes_user_notification_queue: false
- writes_user_session: false
- writes_user_sim_tables: false
- starts_worker: false
- actual_push: false
- real_trade: false

## Next Gate

N6 projection dry-run review
