# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Contract

- result: `CONTRACT_PASS`
- mode: artifact only, no execute, no DB write
- source_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- projection_run_id: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- notification_queue_policy: `deferred`

## Input Scope

Only canonical N5 action events are accepted:

- ActionExecuted pending: `7`
- ActionBlocked pending: `549`
- total pending: `556`
- delivered/delivering: `0/0`

Legacy ActionEvent/HintEvent/RiskEvent/PositionEvent and N4 Trigger* events are not accepted by this contract.

## Planned Writes

- user_projection_run: `1`
- user_signal_projection: `556`
- user_signal_card: `556`
- user_notification_queue: `0`
- user_signal_decision/session/watchlist/sim/order/trade/position/pnl: `0`
- N5 outbox status updates: `0`

## Projection Semantics

- ActionExecuted means `市场动作确认成立`; it does not mean order, trade, delivery, push, voice, mobile, sim, position, PnL, real trade, or proposal.
- ActionBlocked means `市场动作未确认`; blocked_reason is preserved and it must not be shown as an executable recommendation.
- BUY_HINT/SELL_HINT are preserved only as trace/policy context, not as N5 event types.

## Rollback

Rollback SQL: `sql/N6_projection_20260608_until_1500_unified_output_retry_rollback.sql`.
It hard-fails before delete if linked notification/delivery/push/voice/mobile/decision/sim/order/trade/position/pnl/virtual refs exist, and deletes only scoped N6 rows in queue/card/projection/run order.
