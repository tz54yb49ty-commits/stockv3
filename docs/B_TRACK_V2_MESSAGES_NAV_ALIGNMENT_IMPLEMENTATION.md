# B Track V2 Messages Nav Alignment Implementation

Result: IMPLEMENTATION_PASS

Gate: B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION_GATE

Layer role: N6_user

Date: 2026-06-14

## Scope

This implementation aligns B-track user-facing wording around monitor messages. It changes only visible labels, navigation names, page titles, dashboard entry text, and tests.

No route path, API path, DB field, internal enum, N4/N5/N6 fact, effective monitor scope, or message query logic was changed.

## Modified Files

- `src/ashare_v3/web/n6_app_v1.py`
- `src/ashare_v3/web/templates/n6_app_shell.html`
- `tests/test_n6_user_app.py`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION.md`
- `docs/B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION.json`

## Navigation Proof

Implemented visible navigation labels:

- `/n6/app/messages` -> `消息总览`
- `/n6/app/signals` -> `消息列表`
- `/n6/app/my-monitor` -> `监控对象`
- `/n6/app/status-monitor` -> `状态监控`

Implemented page titles:

- `/n6/app/messages` -> `我的监控消息总览`
- `/n6/app/signals` -> `我的监控消息列表`
- `/n6/app/my-monitor` -> `我的监控对象`
- `/n6/app/status-monitor` -> `状态监控`

Dashboard copy now exposes:

- `我的监控消息`
- `查看消息总览`
- `查看消息列表`

Signals-page visible wording is now message-oriented:

- `我的监控消息列表`
- `消息`
- `消息详情`

## Compatibility Proof

Preserved paths:

- `/n6/app/signals`
- `/api/n6/app/v1/signals`
- `/api/n6/app/v1/signals/{user_signal_projection_id}`

Preserved internal/API fields:

- `signal_type`
- `user_signal_projection_id`
- `user_signal_card_id`
- `user_projection_run_id`
- `action_state`
- `action_mark`
- `event_type`
- `projection_run_id`
- `source_run_id`
- `identity_key`
- `condition_key`
- `principal_id`
- `principal_type`

## Forbidden Source Proof

No new source read was introduced. B-track signal/message code remains scoped to reviewed N6 projection/card and effective monitor scope. This gate did not add reads from:

- `common_event_outbox`
- raw K
- direct live market
- N4/N5 raw facts bypass
- `condition_basis`
- `condition_pool`
- `minute_target_scope`

## Forbidden Scope Proof

This gate did not:

- write database business facts
- modify N4/N5/N6 facts
- modify DB schema or internal enums
- consume or update outbox
- start worker
- generate proposal/order/trade
- update position/PnL
- submit real trade

## Tests

Targeted tests covered:

- B-track navigation label alignment
- dashboard message summary copy and links
- signals page copy using message terms while keeping internal API fields
- route/API compatibility
- existing B-track signal, detail, dashboard, monitor, and shell rendering paths

Full validation was run after implementation; see the JSON artifact for command-level proof.

## Decision

IMPLEMENTATION_PASS.

This is ready for `B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_POST_REVIEW_GATE`.
