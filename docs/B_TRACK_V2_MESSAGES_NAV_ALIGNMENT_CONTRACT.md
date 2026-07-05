# B Track V2 Messages Navigation Alignment Contract

## Result

`CONTRACT_PASS`

This contract freezes the B Track V2 user-facing information architecture for monitor messages, scoped signals, status monitoring, and monitor objects. It is a product design / contract artifact only. It does not authorize code changes, database writes, worker execution, projection runs, outbox consumption, or any N6 delivery path.

## Background

Completed prerequisites:

- `B_TRACK_V2_MONITOR_SCOPED_SIGNALS_COMPLETE`
- `B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_COMPLETE`

Existing routes:

- `/n6/app/messages`: current monitor message dashboard.
- `/n6/app/signals`: current effective monitor message list, historically named signals.
- `/n6/app/status-monitor`: current effective monitor status monitor.
- `/n6/app/my-monitor`: user monitor objects.

## Navigation Recommendation

V2 should use message-first naming for ordinary users:

| Route | V2 navigation label | V2 page title | Purpose |
|---|---|---|---|
| `/n6/app/my-monitor` | `监控对象` | `我的监控对象` | Maintain and review the effective monitor scope. |
| `/n6/app/messages` | `消息总览` | `我的监控消息总览` | Aggregate monitor message counts, groups, projection status, and empty-state reasons. |
| `/n6/app/signals` | `消息列表` | `我的监控消息列表` | Row-level user-facing monitor messages and detail drilldown. |
| `/n6/app/status-monitor` | `状态监控` | `当前有效监控状态监控` | Current state of monitored objects, including pending/inactive reasons and coverage blockers. |

The word `信号` should not appear as a primary navigation label for ordinary users in V2. It may remain in internal API names, table names, source fields, compatibility docs, and developer trace.

## Page Tree

```text
我的监控
├── 监控对象        (/n6/app/my-monitor)
├── 消息总览        (/n6/app/messages)
├── 消息列表        (/n6/app/signals)
└── 状态监控        (/n6/app/status-monitor)
```

If the shell has a broader product nav, this group should remain under the N6 user app area and should not be mixed with proposal, order, trade, position, PnL, sim, voice, or mobile delivery surfaces.

## Relationship Between Messages And Signals

User-facing term:

- `消息` means a user-visible N6 projection/card/message derived from approved upstream runtime facts.

Internal compatibility term:

- `signal` remains an internal and API compatibility term for the existing V2 route, source projection, and data model names.

Mapping:

- One `user_signal_projection` row may be shown as one monitor message or message-list item.
- `user_signal_card` is the card/display projection for a message.
- `user_notification_queue` is a later delivery queue and is not part of this read-only dashboard/list contract.
- N4/N5 runtime events remain canonical upstream facts; the V2 user app should present them as monitor messages rather than exposing `signal` as a peer concept.

## Should `/n6/app/signals` Be Renamed?

V2 decision:

- Do not rename the route path.
- Do rename the user-facing label to `消息列表`.
- Do rename detail copy from `信号详情` to `消息详情` in a future implementation gate.
- Keep `/n6/app/signals` and `/api/n6/app/v1/signals` for backward compatibility.

Reason:

- The route and API names are already complete and tested.
- Renaming routes now would create avoidable compatibility risk.
- The user confusion is caused by visible copy, not by the internal path.

## Dashboard Homepage Summary

The dashboard or N6 app homepage should display a compact `我的监控消息摘要` block:

- Today's monitor message count.
- Counts by canonical message/event category, such as `ActionExecuted`, `ActionBlocked`, `TriggerPendingMarketData`, and `TriggerStateChanged`.
- Projection status and last projection run status.
- Empty-state reason if no messages exist.
- Primary link: `查看消息总览` to `/n6/app/messages`.
- Secondary link: `查看消息列表` to `/n6/app/signals`.

The summary must not imply order placement, simulated trading, voice delivery, mobile delivery, or real trading.

## Status Monitor Boundary

`消息总览` and `消息列表` answer:

- What user-visible monitor messages exist today?
- Which message groups are present?
- Which projected cards can the user inspect?
- Why are there no messages?

`状态监控` answers:

- Which monitored objects are currently active, pending, inactive, or blocked?
- Which objects have missing projection, missing metric, stale context, or quality blockers?
- Why did an effective monitor object not produce a message?

Boundary rule:

- `状态监控` may explain absence of a message.
- `状态监控` is not a message inbox and must not duplicate the full message-list experience.
- `消息列表` may link to status details when a message is absent or blocked, but it remains a user-facing message surface.

## User Journey

1. User opens `监控对象` to verify the effective monitor list.
2. User opens `消息总览` to see whether the monitored scope produced any user-facing messages.
3. User opens `消息列表` to inspect individual messages and detail evidence.
4. If expected objects have no message, user opens `状态监控` to understand pending, inactive, or quality blocker reasons.
5. User returns to `消息总览` after a projection refresh or next scheduled update.

## API Compatibility Recommendation

V2 keeps APIs unchanged:

- Keep `GET /api/n6/app/v2/message-dashboard`.
- Keep `GET /api/n6/app/v2/message-dashboard/groups`.
- Keep `GET /api/n6/app/v2/message-dashboard/projection-status`.
- Keep existing signals APIs for compatibility.

No V2 API path, database table, internal enum, event type, action state, trigger state, or canonical runtime field should be renamed by this contract.

## V2 Minimal Change Plan

Future implementation should be copy-only and route-compatible:

1. Change visible navigation label for `/n6/app/signals` from `信号` to `消息列表`.
2. Change visible page title for `/n6/app/signals` from signal wording to `我的监控消息列表`.
3. Change visible detail title from `信号详情` to `消息详情`.
4. Keep route paths, API paths, internal handler names, DB tables, and enums unchanged.
5. Keep all APIs GET-only where they are currently read-only.
6. Keep dashboard source boundary projection-only.

## V3 Ideal Plan

V3 may add compatibility aliases after V2 is stable:

- Add `/n6/app/message-list` as a user-facing alias for `/n6/app/signals`.
- Keep `/n6/app/signals` as a compatibility redirect or hidden legacy route.
- Add `/api/n6/app/v3/messages` only after a separate API migration contract.
- Continue using `signal` internally where it names canonical projection records.
- Keep user-facing navigation message-first.

## Forbidden Change List

This gate forbids:

- Changing route paths.
- Changing API paths.
- Changing database schema.
- Changing internal enums or canonical runtime event names.
- Renaming `user_signal_projection`, `user_signal_card`, or existing V2 API handlers.
- Writing database rows.
- Starting workers, schedulers, projection runs, or delivery jobs.
- Consuming or updating outbox, inbox, or checkpoint rows.
- Reading raw K data, direct live market data, N4/N5 raw facts bypass, `condition_basis`, `condition_pool`, or `minute_target_scope`.
- Reading or consuming `user_notification_queue`.
- Entering N6 delivery, voice, mobile, sim, position, PnL, proposal, order, trade, or real trading paths.

## Validation Contract

Required validation for this gate:

- JSON parse for contract and dry-run artifacts.
- Forbidden wording scan for accidental authorization wording.
- GET-only route boundary review.
- No API, DB, or internal enum change assertion.
- `git diff --check` for the created artifacts.

## Decision

`CONTRACT_PASS`

Proceed to a future copy-only implementation gate:

`B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION_GATE`

