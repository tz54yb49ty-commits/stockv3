# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: n5_live_tracking_20260702__trigger_provisional_ordinary_20260702_until_0944__realtime_action_confirmation_metric_20260702_until_0944__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1__raw_prevday_c1_amount_v1
- user_projection_run_id: n6_user_projection_20260702_0944__n5_live_tracking_raw_prevday_c1_amount_v1
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 64
- by_event_type: {'ActionEligible': 60, 'ActionExecuted': 4}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 64
- user_signal_card: 64
- user_notification_queue: 64
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 64
- target_price_missing: 64
- expected_return_pct_missing: 64
- display_basis_missing: 64
- board_context_missing: 64

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
