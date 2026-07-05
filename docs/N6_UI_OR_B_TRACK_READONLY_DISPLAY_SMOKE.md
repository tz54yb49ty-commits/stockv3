# N6 UI / B-Track Readonly Display Smoke

Result: `DISPLAY_SMOKE_PASS`

Gate: `N6_UI_OR_B_TRACK_READONLY_DISPLAY_SMOKE_GATE`

Layer: `N6_user`

## Scope

This gate only smoke-tested readonly display evidence for the registered N6 projection/card rows.

- `trade_date=20260617`
- `projection_run_id=v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1`
- `source_action_run_id=action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

No UI/API code was modified by this gate. The working tree already contained pre-existing UI/API changes; this gate generated only these smoke artifacts.

## Input Proof

- Display review artifact: `docs/N6_UI_OR_B_TRACK_READONLY_DISPLAY_REVIEW_OR_NEXT_BUSINESS.json`
- Display review result: `DISPLAY_REVIEW_PASS`
- Readonly refresh registration: `docs/N6_UI_OR_B_TRACK_READONLY_REFRESH_POST_REVIEW_REGISTRATION.json`
- Registration result: `REGISTRATION_PASS`
- Prior post-review result: `POST_REVIEW_PASS`
- `rollback_safe=true`

The local read-only RAG helper returned the relevant refresh/registration/display review artifacts and reported no command execution, no DB writes, no worker start, and no outbox/inbox/checkpoint update.

## Display Row Proof

Live DB proof was run inside `BEGIN READ ONLY`, scoped by `source_action_run_id`.

Rows:

- `user_projection_run=1`
- `user_signal_projection=22`
- `user_signal_card=22`
- `user_notification_queue=0`

Displayed action distribution:

- `ActionExecuted/executed/B_BUY=13`
- `ActionExecuted/executed/S_SELL=9`

Displayed action marks:

- `30m_shrink=6`
- `30m_volume=11`
- `normal=5`

## N5 Outbox Proof

N5 outbox remained unchanged:

- `ActionBlocked/pending=469`
- `ActionExecuted/pending=22`
- `delivered_or_delivering=0`

No outbox consumption or status update was performed.

## Display Source Boundary

B-track app signal reads remain projection-scoped:

- `src/ashare_v3/web/n6_user_app.py:3175`
- `src/ashare_v3/web/n6_user_app.py:3215`

B-track message dashboard source policy explicitly keeps forbidden source reads disabled:

- `common_event_outbox_read=false`
- `condition_basis_read=false`
- `condition_pool_read=false`
- `minute_target_scope_read=false`
- `raw_k_read=false`
- `direct_live_market_read=false`
- `n4_raw_fact_bypass=false`
- `n5_raw_fact_bypass=false`
- `user_notification_queue_read=false`

A-track UI signal reads are projection-scoped and only join `common_event_outbox` by `p.source_event_id` for source event display context:

- `src/ashare_v3/web/n6_user_app.py:5403`
- `src/ashare_v3/web/n6_user_app.py:5460`
- `src/ashare_v3/web/n6_user_app.py:5493`

Checked display files had no `required_periods` or `period_trigger_baseline_trace.required_periods` references.

Conclusion:

- No N4 pending rows are used as display input.
- No `required_periods` inference is used.
- No trigger period inference from `condition_key` or `original_condition_key` is used.
- Projection source layer remains `N5_action`.

## Forbidden Scope

Confirmed not performed:

- rollback execution
- N5 outbox consume/update
- N4 outbox update
- delivery/push/voice/mobile write
- sim/position/order/real trade write
- worker/scheduler start
- old system read/modify
- UI/API code modification

## Allowed Next Prompt

Recommended next gate:

`N6_UI_OR_B_TRACK_NEXT_BUSINESS_GATE_SELECTION`

Purpose: choose the next business-only N6/B-track gate after readonly display smoke registration.

Boundaries: no delivery, push, voice, mobile, sim, position, order, real trade, N5 outbox consumption/status update, worker, or scheduler without a separate authorized final gate.
