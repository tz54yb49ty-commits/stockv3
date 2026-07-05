# N4 Worker Bounded Smoke Idempotency Duplicate Retry Contract

Result: `CONTRACT_PASS`

Prerequisites passed: runner alignment, readiness, planning, and four prior N4 worker smoke post-reviews.

The contract requires execute to pass `--idempotency-scenario-path docs/N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_DUPLICATE_RETRY_SCENARIO.json` and expects:

```text
scenario_enabled=true
injected_duplicate_source_event_count=1
injected_existing_consume_key_count=1
skipped_duplicate_source_event_count=2
accepted_source_event_count=9
common_event_inbox=9
common_event_consumer_checkpoint=9
state/match/outbox=0/0/0
failure_injection_enabled=false
N3 outbox status update=0
N5/N6 writes=0
```

Rollback SQL: `sql/N4_worker_bounded_smoke_20260608_idempotency_duplicate_retry_probe_rollback.sql`.
