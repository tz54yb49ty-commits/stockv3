# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Execute Report

- result: `EXECUTE_PASS`
- runner result: `EXECUTED`
- preflight_result: `PREFLIGHT_PASS`
- committed: `True`
- notification_queue_policy: `deferred`
- runner exit code: `0`

## Row Count Proof

- user_projection_run: `1`
- user_signal_projection: `556`
- user_signal_card: `556`
- user_notification_queue: `0`

## Projection / Card Distribution

- ActionExecuted projection/card: `7/7`
- ActionBlocked projection/card: `549/549`
- blocked_reason price_confirmation_failed: `535`
- blocked_reason amount_confirmation_failed: `14`
- ActionExecuted action_mark normal: `6`
- ActionExecuted action_mark 30m_volume: `1`
- ActionBlocked action_mark null: `549`

## Unified Trace Semantic Proof

- source_action_run_id preserved: `556/556`
- source_trigger_run_id preserved: `556/556`
- metric_run_id preserved: `556/556`
- condition_key/original_condition_key present: `556/556`
- trigger_mark_candidate present: `556/556`
- trigger_period / primary_trigger_period / triggered_periods / all_trigger_periods are preserved in `source_payload_json`: `556/556`
- ActionExecuted remains display-only; no order/trade/delivery semantics.
- ActionBlocked is not an executable recommendation.

## N5 Outbox Unchanged

- ActionExecuted pending: `7`
- ActionBlocked pending: `549`
- pending total: `556`
- delivered/delivering: `0/0`
- delivery_attempt_refs: `0`
- inbox_refs: `0`

## Forbidden Scope Proof

- notification queue rows for this run: `0`
- N5 inbox/checkpoint/delivery attempt refs: `0`
- decision/sim/order/trade/position/pnl/virtual refs: `0`
- worker/delivery/push/voice/mobile/real_trade/proposal/order/trade: `false`
- old system touched: `false`

## Rollback Proof

Rollback SQL: `sql/N6_projection_20260608_until_1500_unified_output_retry_rollback.sql`

- hard-fail before DELETE/UPDATE: `true`
- guarded refs: notification, delivery, push, voice, mobile, decision, sim, order, trade, position, pnl, virtual
- delete order: user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run
- preserves N5/N4/N3/N2/N1 facts: `true`
- no CASCADE/DROP/TRUNCATE: `true`
- rollback executed: `false`

## Next Gate

Allowed: `N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_POST_REVIEW_GATE`
