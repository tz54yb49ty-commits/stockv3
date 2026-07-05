# N4 Worker Bounded Smoke Larger Scope Contract

Result: `CONTRACT_PASS`

## Prerequisite Proof

```text
larger_scope_readiness=READINESS_PASS
scoped/expanded/trigger_matched/pending_state/idempotency post-review=POST_REVIEW_PASS/POST_REVIEW_PASS/POST_REVIEW_PASS/POST_REVIEW_PASS/POST_REVIEW_PASS
runner/jsonb/idempotency alignment=ALIGNMENT_PASS/FIX_PASS/ALIGNMENT_PASS
```

## Source Readiness

```text
N3 MarketSnapshotUpdated pending=2155
selected source events=100
selected pending=100/100
delivered/delivering=0
event_id/event_schema_version/dedup_key/partition_key/payload_json=100/100/100/100/100
snapshot/pull_plan/subscription/source_adapter/quality=100/100/100/100/100
existing consume keys for target consumer=0
N3 outbox locked/updated/consumed=false
```

## Dry-Run Summary

```text
accepted_source_event_count=100
skipped_duplicate_source_event_count=0
transition_event_plan_count=0
TriggerMatched=0
TriggerPendingMarketData=0
TriggerStateChanged=0
```

## Planned Write Scope

```text
common_trigger_run=1
common_trigger_quality_item=2
common_event_inbox=100
common_event_consumer_checkpoint=100
common_trigger_state=0
common_trigger_match=0
common_event_outbox=0
N3 outbox status update=0
N5/N6 refs=0
```

## Baseline Proof

```text
target baseline total=0
run/quality/state/match/outbox/inbox/checkpoint=0/0/0/0/0/0/0
downstream refs total=0
```

## Rollback Proof

```text
rollback_sql=sql/N4_worker_bounded_smoke_20260608_larger_scope_probe_rollback.sql
hard_fail_before_first_DELETE_UPDATE=True
guards delivered/delivering and downstream refs=True/True
no_CASCADE_DROP_TRUNCATE=True
rollback_not_executed=true
```

## Quality

```text
P0/P1/P2=0/1/0
blockers=[]
```

P1 is advisory: larger scope smoke is consumption-only and not long-running worker approval.

## Forbidden Scope

No smoke execute, DB write, N3 outbox consume/update, N5/N6 entry, worker start, delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or old-system touch was performed by this gate.

Next gate:

```text
N4_WORKER_BOUNDED_SMOKE_LARGER_SCOPE_EXECUTE_USER_CONFIRMATION_GATE
```
