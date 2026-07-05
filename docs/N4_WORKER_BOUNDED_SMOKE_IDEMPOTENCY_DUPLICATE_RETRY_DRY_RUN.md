# N4 Worker Bounded Smoke Idempotency Duplicate Retry Dry Run

Result: `DRY_RUN_PASS`

Scenario enabled with `docs/N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_SCENARIO.json`.

```text
selected source events=10
injected duplicate source rows=1
injected existing consume keys=1
accepted source events=9
skipped duplicate source events=2
TriggerMatched/TriggerPendingMarketData/TriggerStateChanged=0/0/0
planned run/quality/inbox/checkpoint/state/match/outbox=1/2/9/9/0/0/0
N3 outbox status update=0
N5/N6 writes=0
```

No smoke was executed and no database writes were performed.
