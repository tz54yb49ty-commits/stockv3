# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Dry-Run

- result: `DRY_RUN_PASS`
- layer_role: `N6_user`
- source_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- user_projection_run_id: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- input events: `556`
- ActionExecuted: `7`
- ActionBlocked: `549`
- P0/P1/P2: `0/5/2`
- notification_queue_policy: `deferred`

## Effective Planned Writes

- user_projection_run: `1`
- user_signal_projection: `556`
- user_signal_card: `556`
- user_notification_queue: `0`
- user_signal_decision: `0`
- user_session: `0`
- n5_outbox_status_updates: `0`
- n6_inbox_checkpoint: `0`

## Raw Planner Note

The read-only planner produced `556` notification candidates with `queued_only` semantics. This gate defers notification materialization, so the effective execute contract writes `0` rows to `user_notification_queue` and must block before DB write if queue rows would be inserted.

## Distribution

- ActionBlocked buy/B_BUY: `409`
- ActionBlocked sell/S_SELL: `140`
- ActionExecuted buy/B_BUY: `6`
- ActionExecuted sell/S_SELL: `1`

## Warnings

Display-only warnings are non-blocking and must not trigger N4/N3/N2 backfill from naked facts:

- display_basis_missing: `556`
- current_price_missing: `556`
- target_price_missing: `556`
- expected_return_pct_missing: `556`
- board_context_missing: `556`

## Boundary

- dry-run only: `true`
- writes_database: `false`
- consume/update N5 outbox: `false`
- notification queue write: `false`
- worker/delivery/push/voice/mobile: `false`
- sim/position/pnl/real trade: `false`
- proposal/order/trade: `false`
