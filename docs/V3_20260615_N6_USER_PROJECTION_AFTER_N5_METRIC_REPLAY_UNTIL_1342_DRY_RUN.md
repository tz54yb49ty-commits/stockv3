# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1342_v1
- user_projection_run_id: v3_n6_user_projection_20260615_after_n5_metric_replay_until_1342_v1
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 871
- by_event_type: {'ActionBlocked': 867, 'ActionExecuted': 4}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 871
- user_signal_card: 871
- user_notification_queue: 871
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 871
- target_price_missing: 871
- expected_return_pct_missing: 871
- display_basis_missing: 871
- board_context_missing: 871

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
