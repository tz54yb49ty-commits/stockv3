# N4 Worker Bounded Polling Scheduler Reactivation Report

Result: `BLOCKED`

Layer role: `N4_trigger`

## Reactivation Proof

- target label: `com.ashare-v3.n4.bounded-polling`
- target plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.bounded-polling.plist`
- plist lint: `PASS`
- command executed: `launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n4.bounded-polling.plist`
- bootstrap result: `PASS`
- launchctl state snapshot: `not running`
- launchctl runs observed: `5`
- launchctl last exit code: `2`
- run interval: `60 seconds`
- manual wrapper execution: `false`
- manual child runner execution: `false`

## Blocker

The scheduler was reactivated successfully, and the first automatic bounded pass completed with `EXECUTE_PASS`.

The repeated scheduled pass then failed in the child bounded smoke runner:

```text
psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "uq_common_event_inbox_consumer_event"
DETAIL: Key (consumer_name, event_id)=(n4_trigger_worker_v1_bounded_polling_20260611, evt_5502a6acc3728e3b55c95c088ac9b5ebd62daaf0) already exists.
```

Root cause: the polling runner keeps selecting the same N3 pending source events across scheduled runs. Because N3 outbox status is intentionally not updated, the next run must skip already-inboxed events or advance selection by consumer inbox/checkpoint state. That cross-run inbox idempotency guard is not yet present.

## First Automatic Pass

- smoke run: `n4_worker_bounded_poll_20260611_20260611T180818+0800`
- result: `EXECUTE_PASS`
- scoped N4 database writes: `true`
- worker started: `false`
- long-running worker started: `false`
- N3 outbox status updated: `false`
- N5/N6 entered: `false`
- common_trigger_run: `1`
- common_trigger_quality_item: `2`
- common_event_inbox: `50`
- common_event_consumer_checkpoint: `50`
- common_trigger_state: `0`
- common_trigger_match: `0`
- common_event_outbox: `0`
- TriggerMatched / TriggerPendingMarketData / TriggerStateChanged: `0 / 0 / 0`

## Latest Failed Pass

- latest failed smoke run: `n4_worker_bounded_poll_20260611_20260611T181247+0800`
- latest wrapper result: `BLOCKED`
- child return code: `1`
- child argv python: `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3`
- bare `python3` used: `false`
- failed run scoped trigger/outbox rows: all `0`

## Boundary Proof

- active wrapper/child process count: `0`
- N3 `MarketSnapshotUpdated` outbox status: `{'pending': 2100}`
- N3 delivered/delivering: `0`
- consumer inbox/checkpoint totals: `50 / 50`
- N4 polling run count: `1`
- N5 action refs for first success/latest failed run: `0`
- N6/user refs: not entered by this gate

## Forbidden Scope Proof

No manual wrapper/N4 child runner execution was performed. No N3 outbox consume/update, N5/N6 entry, delivery/push/voice/mobile, sim/position/PnL/real trade, proposal/order/trade, rollback SQL, or old-system touch occurred. The scheduler remains loaded at this report snapshot; because it is now repeatedly failing, the recommended next gate is to stop/pause it before code repair.

Next gate: `N4_WORKER_BOUNDED_POLLING_SCHEDULER_STOP_OR_PAUSE_GATE`.
