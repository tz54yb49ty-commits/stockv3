# N6 Projection Dry-Run Report

## Summary

- result: DRY_RUN_PASS
- layer_role: N6_user
- source_action_run_id: n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
- user_projection_run_id: user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
- blockers: []
- warnings: ['board_context_missing', 'current_price_missing', 'display_basis_missing', 'expected_return_pct_missing', 'target_price_missing']
- P0/P1/P2: 0/5/2

## Input Events

- input_event_count: 200
- by_event_type: {'ActionBlocked': 199, 'ActionExecuted': 1}

## Planned Rows

- user_projection_run: 1
- user_signal_projection: 200
- user_signal_card: 200
- user_notification_queue: 200
- user_signal_decision: 0
- user_sim_rows: 0

## Missing Fields

- current_price_missing: 200
- target_price_missing: 200
- expected_return_pct_missing: 200
- display_basis_missing: 200
- board_context_missing: 200

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

```text
notification_queue_policy=deferred
dry_run_candidate_user_notification_queue=200
future_execute_user_notification_queue_rows=0
planned_row_counts_deferred={"common_position_event": 0, "common_position_state": 0, "delivery_push_voice_mobile": 0, "n5_outbox_consumption": 0, "n5_outbox_status_updates": 0, "proposal_order_trade": 0, "real_trade": 0, "user_notification_queue": 0, "user_projection_run": 1, "user_session": 0, "user_signal_card": 200, "user_signal_decision": 0, "user_signal_projection": 200, "user_sim_order": 0, "user_sim_position": 0, "user_sim_trade": 0, "user_watchlist": 0, "user_watchlist_item": 0}
reason=Dry-run notification rows are queued-only candidates. This contract/preflight defers notification queue writes, so the authorized future execute must write zero user_notification_queue rows.
```
