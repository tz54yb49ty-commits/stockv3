# N3/N4/N5 20260612 Scheduler Reactivation Final Gate After B2 Fact-Only Schema Constraint Repair

Result: `PASS`

## Repair Proof

- repair report: `docs/N3_20260612_B2_FACT_ONLY_PROJECTION_SCHEMA_CONSTRAINT_COMPATIBILITY_REPAIR.json`
- repair result: `IMPLEMENTATION_PASS`
- root cause: fact-only B2 projection `snapshot_time` could exceed `window_end` at a half-hour boundary when source B1 `snapshot_time` carried seconds or microseconds.
- row-builder validation against the historical `1357` contract: `2082` rows, `0` rows with `snapshot_time > window_end`.

## Validation

- targeted tests: `61 OK`
- compileall: `PASS`
- JSON parse: `PASS`
- forbidden scope scan: `PASS`
- `git diff --check`: `PASS`
- untracked artifact whitespace check: `PASS`

## Scheduler Precheck

- label: `com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll`
- plist: `/Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist`
- `launchctl print` exit code: `113`
- state: `not_loaded`
- wrapper / child process count: `0`

Allowed reactivation command:

```bash
launchctl bootstrap gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

Stop command registry:

```bash
launchctl bootout gui/$(id -u) /Users/chuanfuchen/Library/LaunchAgents/com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll.plist
```

## Forbidden Scope

This final gate did not start the scheduler, manually execute wrapper/N3/N4/N5, write DB, run rollback, consume/update outbox/inbox/checkpoint, enter N6, or touch voice/mobile/sim/trade.

Decision: `ALLOW_REACTIVATION`.
