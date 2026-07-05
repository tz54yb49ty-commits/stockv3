# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
- user_projection_run_id: user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 863
- by_event_type: {'ActionBlocked': 863}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 863
- user_signal_card: 863
- user_notification_queue: 863
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 863
- target_price_missing: 863
- expected_return_pct_missing: 863
- display_basis_missing: 863
- board_context_missing: 863

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
