# N4 Worker Bounded Smoke Idempotency Duplicate Retry Preflight

Result: `PREFLIGHT_PASS`

Live target baseline is clean:

```text
run/quality/state/match/outbox/inbox/checkpoint=0/0/0/0/0/0/0
N3 MarketSnapshotUpdated pending=2155
selected source events=10, all pending
existing consume keys for target consumer=0
```

Preflight confirms accepted source events stay within max_events and checkpoint writes remain bounded. No N3/N5/N6 path is enabled.
