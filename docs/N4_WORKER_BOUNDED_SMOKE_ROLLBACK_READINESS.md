# N4 Worker Bounded Smoke Rollback Readiness

Result: `READINESS_PASS`

## Registration Prerequisite Proof

```text
rollout registration=REGISTRATION_PASS
scoped consumption smoke=POST_REVIEW_PASS
expanded consumption smoke=POST_REVIEW_PASS
larger scope consumption smoke=POST_REVIEW_PASS
TriggerMatched semantic smoke=POST_REVIEW_PASS
Pending+StateChanged semantic smoke=POST_REVIEW_PASS
idempotency / duplicate / retry smoke=POST_REVIEW_PASS
this gate authorizes rollback execution=false
```

## Live Scoped Row Proof

```text
scoped consumption run/quality/inbox/checkpoint/state/match/outbox=1/2/5/5/0/0/0
expanded consumption run/quality/inbox/checkpoint/state/match/outbox=1/2/50/50/0/0/0
larger scope consumption run/quality/inbox/checkpoint/state/match/outbox=1/2/100/100/0/0/0
TriggerMatched semantic run/quality/inbox/checkpoint/state/match/outbox=1/2/10/10/10/10/10
Pending+StateChanged semantic run/quality/inbox/checkpoint/state/match/outbox=1/2/6/6/6/0/8
idempotency duplicate retry run/quality/inbox/checkpoint/state/match/outbox=1/2/9/9/0/0/0
```

N4 outbox status:

```text
TriggerMatched semantic pending/delivered/delivering=10/0/0
Pending+StateChanged semantic pending/delivered/delivering=8/0/0
all consumption-only smoke outbox rows=0
```

## Downstream Refs Proof

Business downstream refs are zero for all six smoke lineages:

```text
N5 common_action_run/common_action_event=0/0
stock/index/board_action_fact refs=0/0/0
N6 user projection/card/notification refs=0
delivery/push/voice/mobile refs=0
sim/order/trade/position/pnl refs=0
```

Scoped smoke inbox/checkpoint rows are part of each smoke lineage and are not treated as downstream blockers.

## N3 Preservation Proof

Source N3 stream:

```text
N3 MarketSnapshotUpdated total=2155
pending=2155
delivered=0
delivering=0
```

Persisted smoke inbox source events remain pending:

```text
scoped consumption=5/5
expanded consumption=50/50
larger scope consumption=100/100
TriggerMatched semantic=10/10
Pending+StateChanged semantic=6/6
idempotency duplicate retry accepted persisted rows=9/9
```

`idempotency_duplicate_retry` modeled 10 selected source events in its post-review, with 9 persisted accepted inbox rows after one modeled existing consume key. N3 outbox status remains unchanged.

## Rollback SQL Proof

All target rollback SQL files exist and are hard-fail guarded before the first executable `DELETE` / `UPDATE`:

```text
sql/N4_worker_bounded_smoke_20260608_unified_output_probe_rollback.sql
sql/N4_worker_bounded_smoke_20260608_unified_output_expanded_probe_rollback.sql
sql/N4_worker_bounded_smoke_20260608_larger_scope_probe_rollback.sql
sql/N4_worker_bounded_smoke_20260608_trigger_semantic_probe_rollback.sql
sql/N4_worker_bounded_smoke_20260608_pending_state_changed_semantic_fixture_probe_rollback.sql
sql/N4_worker_bounded_smoke_20260608_idempotency_duplicate_retry_probe_rollback.sql
```

Proof:

```text
scoped by exact smoke_run_id=true
scoped by exact consumer_name=true
guards N4 delivered/delivering=true
guards N5/N6/user/sim/order/trade/position refs=true
does not touch N3 facts/outbox status=true
no CASCADE/DROP/TRUNCATE=true
rollback executed=false
```

The generic template `sql/N4_worker_bounded_smoke_rollback.sql` also remains hard-fail guarded and was not executed.

## Readiness Decision

```text
rollback_executable_now=false
requires separate rollback final gate and user confirmation=true
all lineages are rollback-ready if a future final gate authorizes=true
lineages with N4 outbox rows=TriggerMatched semantic, Pending+StateChanged semantic
lineages with N4 outbox rows must remain guarded by delivered/delivering=0 and downstream refs=0
if any downstream refs exist, rollback must proceed reverse order=true
if preserving smoke evidence is preferred, no rollback needed now=true
existing smoke rows are acceptable as registered bounded evidence=true
```

## Forbidden Scope

This gate did not execute rollback SQL, write the database, consume/update N3 outbox, enter N5/N6, start worker, touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Validation

```text
JSON parse PASS
live scoped row proof PASS
downstream refs scan PASS
N3 preservation proof PASS
rollback SQL static check PASS
git diff --check PASS
```

Recommended next gate:

```text
N4_WORKER_BOUNDED_SMOKE_500_SCOPE_READINESS_GATE
```
