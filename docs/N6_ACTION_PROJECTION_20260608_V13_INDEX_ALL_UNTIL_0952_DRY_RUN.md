# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
- user_projection_run_id: user_projection_dry_run_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 201
- by_event_type: {'ActionEligible': 201}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 201
- user_signal_card: 201
- user_notification_queue: 201
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 201
- target_price_missing: 201
- expected_return_pct_missing: 201
- display_basis_missing: 201
- board_context_missing: 201

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
