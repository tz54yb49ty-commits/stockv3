# N4 Worker Rollout Policy Contract

Result: `CONTRACT_PASS`

## Evidence Scope Accepted

The following evidence is accepted for N4 bounded worker readiness only:

```text
bounded consumption smoke covered event counts=5/50/100/500/1000/2000
TriggerMatched semantic smoke=POST_REVIEW_PASS
TriggerPendingMarketData semantic path=POST_REVIEW_PASS
TriggerStateChanged semantic path=POST_REVIEW_PASS
idempotency / duplicate / retry smoke=POST_REVIEW_PASS
N3 outbox updated or consumed in smoke=false
N5/N6/downstream refs in smoke=0
long-running worker approval=false
```

This evidence proves bounded smoke readiness and rollout-policy readiness. It does not approve any long-running worker, N3 outbox status mutation, N5 worker, N6 delivery, sim, or trade path.

## Stage Model

### A. `bounded_smoke_registered`

Entry criteria:

```text
rollout registration refresh=REGISTRATION_PASS
bounded consumption smoke through 2000 events=POST_REVIEW_PASS
semantic event-path smoke=POST_REVIEW_PASS
idempotency duplicate retry smoke=POST_REVIEW_PASS
```

Allowed writes:

```text
none in this policy gate
```

Forbidden writes:

```text
N3/N4/N5 outbox/inbox/checkpoint mutation
N4/N5/N6 execute writes
worker start
delivery/sim/trade
```

Rollback requirements:

```text
existing smoke rows are registered evidence and must not be silently deleted
future rollback must be scoped by smoke_run_id and consumer_name
```

Exit criteria:

```text
registration artifact records accepted bounded evidence and remaining blockers
```

### B. `rollout_policy_contract`

Entry criteria:

```text
bounded_smoke_registered complete
runtime canonical specs reviewed
continuous state transition contract=CONTRACT_PASS
```

Allowed writes:

```text
docs/N4_WORKER_ROLLOUT_POLICY_CONTRACT.md
docs/N4_WORKER_ROLLOUT_POLICY_CONTRACT.json
```

Forbidden writes:

```text
database writes
outbox/inbox/checkpoint mutations
worker start
N4/N5/N6 execute
```

Rollback requirements:

```text
documentation-only rollback is git revert / artifact supersession
business rollback not applicable
```

Exit criteria:

```text
policy contract=CONTRACT_PASS
P0=0
P1 blockers documented
```

### C. `day_scope_dry_run`

Entry criteria:

```text
rollout_policy_contract=CONTRACT_PASS
source N3 run selected
day-scope dry-run contract defines max_events/day window and no-write mode
```

Allowed writes:

```text
dry-run/report artifacts only
```

Forbidden writes:

```text
N3 outbox status update
N4 trigger state/match/outbox writes
N4 inbox/checkpoint writes unless a later bounded execute gate authorizes them
N5/N6 writes
worker start
```

Rollback requirements:

```text
not applicable for no-write dry-run artifacts except artifact supersession
```

Exit criteria:

```text
day-scope input/event count proof
estimated lag/throughput proof
P0 blockers=0 before any larger bounded execute proposal
```

### D. `n5_worker_planning`

Entry criteria:

```text
N4 TriggerMatched outbox lineage selected
N5 run-once / semantic action evidence available
N4 output and N5 entry policy accepted
```

Allowed writes:

```text
N5 worker planning / readiness / contract artifacts only
```

Forbidden writes:

```text
N4 outbox consumption
N5 action facts/events
N6 projection/notification
worker start
```

Rollback requirements:

```text
N5 worker rollback strategy must be designed before any N5 bounded execute
must guard N6/user/sim/order/trade/position refs
```

Exit criteria:

```text
N5 worker scoped consumption smoke readiness gate may be opened
```

### E. `n4_n5_chained_bounded_smoke`

Entry criteria:

```text
N4 bounded rollout policy=CONTRACT_PASS
N5 worker consumer contract=CONTRACT_PASS
N4 and N5 scoped rollback SQL generated and reviewed
```

Allowed writes:

```text
only explicitly authorized scoped N4/N5 bounded smoke rows
```

Forbidden writes:

```text
N3 outbox status mutation unless separate ack policy final gate approves it
N6/user projection
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
long-running worker
```

Rollback requirements:

```text
reverse-order rollback: N5 before N4 if N5 refs exist
guard delivered/delivering N4/N5 outbox rows
guard all N6/user/sim/order/trade/position refs
```

Exit criteria:

```text
chained bounded smoke post-review=POST_REVIEW_PASS
N3 outbox policy unchanged unless separately approved
```

### F. `shadow_continuous_worker_readiness`

Entry criteria:

```text
day_scope_dry_run complete
n4_n5_chained_bounded_smoke complete or explicitly deferred
lifecycle registry / heartbeat registry design complete
stop / pause-drain policy complete
```

Allowed writes:

```text
readiness/contract artifacts only
```

Forbidden writes:

```text
long-running worker start
unbounded consumption
N3 outbox mutation without ack final gate
N6/delivery/sim/trade
```

Rollback requirements:

```text
must include long-running rollback and supersession strategy
must distinguish smoke rows from long-running lineage rows
```

Exit criteria:

```text
shadow readiness=READINESS_PASS
P0=0
all lifecycle controls auditable
```

### G. `long_running_worker_readiness`

Entry criteria:

```text
shadow_continuous_worker_readiness=READINESS_PASS
ack policy final gate resolved
N5 worker contract/chained smoke resolved or explicitly out of scope
lifecycle / heartbeat / stop / pause-drain registry ready
rollback / supersession policy approved
```

Allowed writes:

```text
readiness/final-gate artifacts only
```

Forbidden writes:

```text
worker start
database writes outside approved readiness artifact generation
delivery/sim/trade
```

Rollback requirements:

```text
long-running rollback must be scoped by run lineage and consumer
supersession must preserve historical smoke evidence
downstream refs require reverse-order rollback
```

Exit criteria:

```text
long_running_worker_readiness=READINESS_PASS
execute user-confirmation command generated but not run
```

### H. `long_running_worker_execute_user_confirmation`

Entry criteria:

```text
long_running_worker_readiness=READINESS_PASS
final gate=PASS
user explicitly authorizes execute
rollback SQL and stop policy reviewed
```

Allowed writes:

```text
only exact final-gate approved worker lineage and lifecycle rows
```

Forbidden writes:

```text
N3 outbox mutation unless ack policy explicitly approved
N5/N6/delivery/sim/trade unless separately approved
old system touch
```

Rollback requirements:

```text
must have tested hard-fail rollback guard
must guard downstream refs
must support pause-drain before rollback when worker is active
```

Exit criteria:

```text
execute report generated
post-review gate required before any next layer action
```

## Lifecycle / Control Policy

Worker execute prerequisites:

```text
contract required=true
preflight required=true
final gate required=true
rollback SQL required=true
user-confirmed execute required=true
```

Bounded worker controls:

```text
max_events required
max_runtime_seconds required
heartbeat_interval_seconds required
stop_file required
status_json required
```

Long-running worker controls:

```text
lifecycle registry required
heartbeat registry required
stop policy required
pause-drain policy required
worker_started auditable=true
long_running_worker_started auditable=true
smoke runner may not be reused as long-running worker without separate final gate
status_json is smoke status only and is not a long-running worker registry
```

## N3 Outbox Ack Policy

Current default:

```text
N4 must not update N3 common_event_outbox.status
N4 must not mark N3 events delivered/delivering
N4 ack is limited to N4-owned common_event_inbox and common_event_consumer_checkpoint
```

Any policy allowing N3 outbox `delivered` / `delivering` mutation requires a separate ack policy migration / final gate. Current bounded smoke evidence must not be interpreted as approval for N3 outbox consumption.

## N4 Output / N5 Entry Policy

Canonical N5 entry:

```text
TriggerMatched is the only N5 entry
TriggerPendingMarketData must not enter N5
TriggerStateChanged must not enter N5
```

N4 write behavior:

```text
TriggerMatched writes common_trigger_match=true
TriggerPendingMarketData writes common_trigger_match=false
TriggerStateChanged writes common_trigger_match=false
```

N5 worker policy:

```text
N5 worker may consume N4 outbox only after a dedicated N5 worker contract gate
current policy authorizes N5 worker=false
current policy authorizes N4 outbox consumption=false
```

## Rollback / Supersession Policy

Smoke rollback:

```text
existing smoke rows are registered evidence and must not be silently deleted
rollback must be scoped by run_id / consumer_name
rollback must guard delivered/delivering N4 outbox
rollback must guard N5/N6/user/sim/order/trade/position refs
downstream refs require reverse-order rollback
```

Long-running rollback:

```text
long-running worker needs a separate supersession policy
smoke rollback SQL must not be reused to clear long-running lineage
supersession must preserve historical evidence and clearly mark active lineage
pause-drain must be available before rollback when worker is active
```

## Remaining Blockers / Required Gates

```text
P0/P1/P2=0/6/0
```

P1 before long-running worker:

```text
lifecycle registry / heartbeat registry
N3 ack/status policy
day-scope dry-run
N5 worker consumer contract
N4->N5 chained bounded smoke
rollback/supersession policy for long-running worker
```

Recommended next gate:

```text
N4_WORKER_DAY_SCOPE_DRY_RUN_GATE
```

Alternative next gate:

```text
N5_WORKER_SCOPED_CONSUMPTION_SMOKE_READINESS_GATE
```

## Forbidden Scope

This policy contract did not execute SQL, write database rows, consume/update N3/N4/N5 outbox/inbox/checkpoint, enter N4/N5/N6 execute, start worker, touch delivery/push/voice/mobile, sim/position/pnl/real_trade, proposal/order/trade, or the old system.

## Validation

```text
JSON parse PASS
referenced artifacts parse PASS
policy consistency with runtime spec PASS
forbidden scope proof PASS
git diff --check PASS
```
