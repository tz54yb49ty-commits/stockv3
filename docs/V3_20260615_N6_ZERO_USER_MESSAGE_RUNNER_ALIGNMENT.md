# V3 20260615 N6 Zero User Message Runner Alignment

- result: `ALIGNMENT_PASS`
- gate: `V3_20260615_N6_ZERO_USER_MESSAGE_RUNNER_ALIGNMENT_GATE`
- layer_role: `N6_user`
- mode: code/test alignment only
- N6 execute performed: `false`
- database write performed: `false`

## Runner Alignment

The N6 projection planner and execute runner now support an explicit `user_message_event_filter`.

- contract setting is read from `user_message_event_filter.include_event_types`
- current product filter: `ActionEligible`, `ActionExecuted`
- `ActionBlocked` and `ActionSkipped` remain source-observed diagnostics/status-monitor events only
- ordinary user projection/card/notification rows are created only for filtered user-message events

When the source is ActionBlocked-only, the runner produces a scoped projection run with zero user messages:

- result: `PROJECTION_PASS_ZERO_USER_MESSAGES`
- user_projection_run: `1`
- user_signal_projection: `0`
- user_signal_card: `0`
- user_notification_queue: `0`

## Fail-Closed Proof

- Explicit source outbox expected distribution is still required for the gate.
- `ActionBlocked:pending=836` must match exactly for the 20260615 gate.
- Mismatched source counts still block with `n5_outbox_count_mismatch_without_new_gate`.
- Missing contract filters block with `missing_user_message_event_filter`.
- Empty user message filters block with `missing_user_message_event_filter`.
- Unknown event types block with `unsupported_user_message_event_filter`.

## Validation

- targeted unittest: `tests.test_n6_projection_plan` and `tests.test_n6_projection_execute` passed, `42` tests total.
- no DB execute path was invoked against the live database.
- no N5 outbox/inbox/checkpoint path was consumed or updated.
- no worker, delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, real trade, or old system path was touched.

## Next Gate

`V3_20260615_N6_USER_PROJECTION_EXECUTE_FINAL_GATE_REVIEW`
