# B Track V2 Messages Navigation Alignment Dry Run

## Result

`DRY_RUN_PASS`

The dry run applies the contract mentally to the current B Track V2 pages without changing code. It confirms that the confusion is a user-facing naming issue, not a route/API/data-model issue.

## Current State Observed

Existing product surfaces:

- `/n6/app/messages` already serves `我的监控消息总览`.
- `/n6/app/signals` is the effective monitor message list but still has compatibility naming around `signals`.
- `/n6/app/status-monitor` tracks current effective monitor state.
- `/n6/app/my-monitor` tracks monitor objects.

Existing implementation evidence:

- `B_TRACK_V2_MONITOR_SCOPED_SIGNALS_COMPLETE`
- `B_TRACK_V2_MONITOR_MESSAGE_DASHBOARD_COMPLETE`
- Message dashboard APIs are GET-only.
- Message dashboard source is projection-only and effective-monitor scoped.

## Dry-Run User Navigation

Recommended V2 navigation after a copy-only implementation:

```text
监控对象
消息总览
消息列表
状态监控
```

Expected user interpretation:

- `监控对象`: what I am watching.
- `消息总览`: what happened across my watchlist today.
- `消息列表`: the detailed message rows.
- `状态监控`: why a watched object is active, pending, inactive, or blocked.

This removes the ordinary-user conflict between `信号` and `消息` while preserving the already-tested compatibility routes.

## `/n6/app/signals` Dry-Run Decision

`/n6/app/signals` should not be route-renamed in V2.

Dry-run label mapping:

| Current route | Future visible label | Compatibility decision |
|---|---|---|
| `/n6/app/signals` | `消息列表` | Keep route path and existing API names. |
| Signal detail copy | `消息详情` | Copy-only change in future implementation. |

No internal table, enum, API path, or handler rename is required for V2.

## Dashboard Summary Dry Run

The dashboard/home summary should display:

- Today's monitor message count.
- Counts by canonical category.
- Projection status.
- Empty-state reason.
- Link to `消息总览`.
- Link to `消息列表`.

It must not display trading intent, order intent, voice delivery, mobile delivery, sim status, real position, or PnL.

## Status Monitor Boundary Dry Run

Example:

- A watched object produced an `ActionExecuted` projection.
  - It appears in `消息总览` and `消息列表`.
- A watched object has no user message because upstream metric is missing.
  - `消息总览` may show an empty-state or excluded reason.
  - `状态监控` explains the object-level blocker.

`状态监控` should help diagnose message absence, not become a second message inbox.

## API Boundary Dry Run

V2 route compatibility is preserved:

- Existing message-dashboard GET APIs remain unchanged.
- Existing signals GET APIs remain unchanged.
- No POST/PATCH/DELETE message-dashboard routes are introduced by this contract.
- No API path is renamed by this contract.

## V2 Minimal Change Dry Run

Future implementation can be limited to:

- User-facing nav label updates.
- User-facing page title updates.
- User-facing detail wording updates.
- Dashboard summary wording alignment.

No backend behavior is required to satisfy this information-architecture gate.

## V3 Ideal Dry Run

After V2 stabilizes, V3 may add:

- `/n6/app/message-list` alias.
- `/api/n6/app/v3/messages` API.
- Compatibility redirect from `/n6/app/signals`.

Those are explicitly out of scope for this V2 contract.

## Forbidden Scope Proof

This dry run does not:

- Modify code.
- Write database rows.
- Start workers, schedulers, or projection runs.
- Consume or update outbox, inbox, or checkpoints.
- Enter N6 delivery.
- Touch voice, mobile, sim, position, PnL, proposal, order, trade, or real trading.
- Read raw K data, direct live market data, N4/N5 raw facts bypass, `condition_basis`, `condition_pool`, `minute_target_scope`, or `user_notification_queue`.

## Dry-Run Decision

`DRY_RUN_PASS`

Recommended next gate:

`B_TRACK_V2_MESSAGES_NAV_ALIGNMENT_IMPLEMENTATION_GATE`

