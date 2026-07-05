# N6 UI / B-Track Readonly Display Review

Result: `DISPLAY_REVIEW_PASS`

Gate: `N6_UI_OR_B_TRACK_READONLY_DISPLAY_REVIEW_OR_NEXT_BUSINESS_GATE`

Layer: `N6_user`

## Scope

This gate only reviewed readonly display readiness for the registered N6 projection:

- `trade_date=20260617`
- `projection_run_id=v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1`
- `source_action_run_id=action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

No UI/API code was modified by this gate. The working tree already contained pre-existing UI/API changes; this gate generated only these review artifacts.

## Artifact Proof

- `docs/N6_UI_OR_B_TRACK_READONLY_REFRESH.json`: `READONLY_REFRESH_PASS`
- `docs/N6_UI_OR_B_TRACK_READONLY_REFRESH_POST_REVIEW_REGISTRATION.json`: `REGISTRATION_PASS`
- Prior post-review result: `POST_REVIEW_PASS`
- `rollback_safe=true`

## Live Readonly Proof

The live DB proof was run inside `BEGIN READ ONLY`.

Scoped rows:

- `user_projection_run=1`
- `user_signal_projection=22`
- `user_signal_card=22`
- `user_notification_queue=0`

Projection distribution:

- `ActionExecuted/executed/B_BUY=13`
- `ActionExecuted/executed/S_SELL=9`

Action marks:

- `30m_shrink=6`
- `30m_volume=11`
- `normal=5`

N5 outbox remained unchanged:

- `ActionBlocked/pending=469`
- `ActionExecuted/pending=22`
- `delivered_or_delivering=0`

## Display Boundary Proof

B-track app signal reads are projection-scoped:

- `src/ashare_v3/web/n6_user_app.py:3175`
- `src/ashare_v3/web/n6_user_app.py:3215`

They read `user_signal_projection`, `user_projection_run`, and `user_signal_card` with passed or ready projection runs.

A-track UI signal reads are also projection-scoped:

- `src/ashare_v3/web/n6_user_app.py:5403`
- `src/ashare_v3/web/n6_user_app.py:5460`
- `src/ashare_v3/web/n6_user_app.py:5493`

The A-track join to `common_event_outbox` is by `p.source_event_id`, which points to the N5 source event for this projection scope. This gate found no checked display-file reference to `required_periods`.

Conclusion:

- N6 display path does not use N4 pending rows as projection input.
- N6 display path does not infer trigger period from `condition_key`, `original_condition_key`, `required_periods`, or pending trace fields.
- `condition_key` and `original_condition_key` remain trace/display fields only.

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

`N6_UI_OR_B_TRACK_READONLY_DISPLAY_SMOKE_GATE`

Purpose: optional live browser/API smoke for readonly display using the registered 20260617 projection rows.

Boundaries: read-only only; no UI/API code modification; no outbox consumption/update; no worker/scheduler; no delivery, voice, mobile, sim, position, order, or real trade.
