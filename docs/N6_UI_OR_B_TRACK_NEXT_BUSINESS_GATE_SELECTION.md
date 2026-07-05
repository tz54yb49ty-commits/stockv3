# N6 UI / B-Track Next Business Gate Selection

Result: `NEXT_BUSINESS_SELECTION_PASS`

Gate: `N6_UI_OR_B_TRACK_NEXT_BUSINESS_GATE_SELECTION`

Layer: `N6_user`

## Scope

This gate only selects the next N6/UI or B-track business gate after readonly display smoke.

- `trade_date=20260617`
- `projection_run_id=v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1`
- `source_action_run_id=action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`

This gate did not execute any business flow and did not modify UI/API code.

## Input Proof

- `docs/N6_UI_OR_B_TRACK_READONLY_DISPLAY_SMOKE.json`: `DISPLAY_SMOKE_PASS`
- `docs/N6_UI_OR_B_TRACK_READONLY_DISPLAY_REVIEW_OR_NEXT_BUSINESS.json`: `DISPLAY_REVIEW_PASS`
- `docs/N6_UI_OR_B_TRACK_READONLY_REFRESH_POST_REVIEW_REGISTRATION.json`: `REGISTRATION_PASS`
- Prior post-review result: `POST_REVIEW_PASS`
- `rollback_safe=true`

The local read-only RAG helper returned the relevant smoke, registration, display review, and post-review artifacts. Its safety flags showed no command execution, no database write, no worker start, and no outbox/inbox/checkpoint update.

## Display Smoke Proof

Rows:

- `user_projection_run=1`
- `user_signal_projection=22`
- `user_signal_card=22`
- `user_notification_queue=0`

Displayed distribution:

- `ActionExecuted/executed/B_BUY=13`
- `ActionExecuted/executed/S_SELL=9`

Action marks:

- `30m_shrink=6`
- `30m_volume=11`
- `normal=5`

N5 outbox unchanged:

- `ActionBlocked/pending=469`
- `ActionExecuted/pending=22`
- `delivered_or_delivering=0`

Display boundary:

- No N4 pending rows used as display input.
- No `required_periods` inference.
- No trigger period inference from `condition_key` or `original_condition_key`.
- No UI/API code modification.

## Selected Next Gate

Selected: `N6_UI_OR_B_TRACK_READONLY_DISPLAY_CLOSEOUT_REGISTRATION_GATE`

Rationale: the current evidence proves readonly display smoke and source boundaries. The minimal safe next step is a read-only closeout registration before expanding into any new dashboard/status closeout, delivery policy design, voice/mobile design, or sim/position/order design.

Deferred alternatives:

- `B_TRACK_READONLY_DASHBOARD_STATUS_CLOSEOUT_GATE`
- `N6_DELIVERY_PUSH_VOICE_POLICY_DESIGN_REVIEW_ONLY_GATE`
- `N6_SIM_POSITION_ORDER_POLICY_DESIGN_REVIEW_ONLY_GATE`

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

```text
layer_role=N6_user.

进入 N6_UI_OR_B_TRACK_READONLY_DISPLAY_CLOSEOUT_REGISTRATION_GATE。

Use:
- trade_date=20260617
- projection_run_id=v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1
- source_action_run_id=action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
- next_business_selection=docs/N6_UI_OR_B_TRACK_NEXT_BUSINESS_GATE_SELECTION.json
- display_smoke_artifact=docs/N6_UI_OR_B_TRACK_READONLY_DISPLAY_SMOKE.json
- display_review_artifact=docs/N6_UI_OR_B_TRACK_READONLY_DISPLAY_REVIEW_OR_NEXT_BUSINESS.json
- readonly_refresh_registration=docs/N6_UI_OR_B_TRACK_READONLY_REFRESH_POST_REVIEW_REGISTRATION.json

目标：
只登记 N6/UI 或 B-track readonly display closeout，不执行下一步业务，不修改 UI/API code，不做 delivery/push/voice/mobile/sim/position/order/real trade。

必须证明：
- next_business_selection result=NEXT_BUSINESS_SELECTION_PASS
- selected_next_gate=N6_UI_OR_B_TRACK_READONLY_DISPLAY_CLOSEOUT_REGISTRATION_GATE
- display_smoke_result=DISPLAY_SMOKE_PASS
- display_review_result=DISPLAY_REVIEW_PASS
- readonly_refresh_registration result=REGISTRATION_PASS
- projection rows: user_projection_run=1, user_signal_projection=22, user_signal_card=22, user_notification_queue=0
- displayed distribution: ActionExecuted/executed/B_BUY=13, ActionExecuted/executed/S_SELL=9
- action marks: 30m_shrink=6, 30m_volume=11, normal=5
- N5 outbox unchanged: ActionBlocked/pending=469, ActionExecuted/pending=22, delivered_or_delivering=0
- no N4 pending rows used as display input
- no required_periods inference
- no UI/API code modification

禁止：
- 不执行 rollback
- 不消费/update N5 outbox
- 不更新 N4 outbox
- 不写 delivery/push/voice/mobile
- 不写 sim/position/order/real trade
- 不启动 worker/scheduler
- 不读取/修改 old system
- 不修改 UI/API code

输出：
CLOSEOUT_REGISTRATION_PASS / BLOCKED
closeout registration artifact path
selection proof
display smoke proof
forbidden scope proof
allowed next prompt
```
