# N3/N4/N5 20260612 Scheduler Stop After B2 Fact-Only Schema Constraint Block

Result: `STOP_PASS`

The scoped LaunchAgent was stopped:

- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist`
- command: `launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist`
- exit code: `0`
- post-check: `launchctl print` returned `113`, service `not_loaded`
- wrapper / child process count: `0`

## Blocked Context

The first reactivation pass after B2 dates compatibility repair blocked in N3-B2 fact-only realtime projection:

- failed effective HHMM: `1357`
- failing constraint: `stock_realtime_projection_metric_check2`
- constraint semantics: `snapshot_time <= window_end`
- evidence: B2 reached `N3-B2 writing 2082 projection facts`, then failed because `projection_snapshot_time=2026-06-12 14:00:00.010889+08` exceeded `window_end=2026-06-12 14:00:00+08`.

Before the scheduler was stopped, a later automatic N3 auto-poll report advanced to `effective_hhmm=1401` and `status=passed`. The boundary bug still needed repair because it can recur at later half-hour boundaries.

## Boundary Proof

- no manual wrapper/N3/N4/N5 execution
- no rollback executed
- no outbox/inbox/checkpoint consumption or update by this stop gate
- no N6 entry
- no voice/mobile/sim/trade touch

Next: `N3_20260612_B2_FACT_ONLY_PROJECTION_SCHEMA_CONSTRAINT_COMPATIBILITY_REPAIR_GATE`.
