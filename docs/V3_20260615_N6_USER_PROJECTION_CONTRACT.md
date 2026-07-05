# V3 20260615 N6 User Projection Contract

- result: `CONTRACT_PASS`
- gate: `V3_20260615_N6_USER_PROJECTION_CONTRACT_REFRESH_GATE`
- mode: artifact only, no execute, no DB write
- source_action_run_id: `n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- notification_queue_policy: `deferred`

## Source Scope

The source N5 action run is passed and contains only canonical N5 action output:

- ActionBlocked pending: `836`
- ActionEligible pending: `0`
- ActionExecuted pending: `0`
- ActionSkipped pending: `0`
- delivered/delivering: `0/0`

Legacy ActionEvent/HintEvent/RiskEvent/PositionEvent are not part of this contract.

## User Message Filter

Product display rule for the ordinary user message list:

- include: `ActionEligible`, `ActionExecuted`
- exclude from user message projection/card/queue: `ActionBlocked`, `ActionSkipped`

ActionBlocked and ActionSkipped remain visible to admin status monitoring / diagnosis paths only. They must not create ordinary user message projection rows, cards, notification queue rows, proposal, order, trade, position, PnL, voice, mobile, push, or real-trade intent.

## Planned Writes

Because the source distribution is ActionBlocked-only and the user message filter includes only ActionEligible/ActionExecuted, expected user-message eligible count is `0`.

- user_projection_run: `1`
- user_signal_projection: `0`
- user_signal_card: `0`
- user_notification_queue: `0`
- user_signal_decision/proposal/order/trade/position/pnl: `0`
- N5 outbox status updates: `0`

Expected result: `PROJECTION_PASS_ZERO_USER_MESSAGES`.

## Rollback

Rollback SQL: `sql/V3_20260615_N6_USER_PROJECTION_ROLLBACK.sql`.

The rollback hard-fails before any DELETE/UPDATE if linked delivery, notification, push, voice, mobile, decision, sim, virtual order/trade/position/PnL, proposal, or real-trade refs exist. Its deletion scope is only the fixed `projection_run_id` above and it does not touch N5/N4/N3/N2/N1 facts, outbox status, inbox, checkpoint, scheduler, or old system.
