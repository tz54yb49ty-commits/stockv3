# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
- user_projection_run_id: user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 119
- by_event_type: {'ActionBlocked': 119}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 119
- user_signal_card: 119
- user_notification_queue: 119
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 119
- target_price_missing: 119
- expected_return_pct_missing: 119
- display_basis_missing: 119
- board_context_missing: 119

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

## Runtime Control Deferred Contract Note

The raw dry-run planner found `119` queued-only notification candidates. This contract gate uses `notification_queue_policy=deferred`, so future execute planned writes keep `user_notification_queue=0` and write only `user_projection_run`, `user_signal_projection`, and `user_signal_card`.
