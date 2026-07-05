# N4 / N5 Worker Rollout Planning

Result: `PLANNING_PASS`

Gate: `N4_N5_WORKER_ROLLOUT_PLANNING_GATE`

Generated at: `2026-06-10T09:58:54+08:00`

## Decision

N4 has enough evidence to continue with larger bounded worker rollout gates, but not enough evidence to start a long-running worker.

N5 has strong run-once evidence, but it does not yet have worker smoke evidence. N5 worker rollout must start with its own scoped consumption smoke after N4 event stream semantics are further stabilized.

## P0/P1/P2

| severity | count |
|---|---:|
| P0 | 0 |
| P1 | 6 |
| P2 | 0 |

P1 items are rollout gaps, not blockers for this planning gate.

## N4 Worker Readiness Summary

Passed evidence:

| evidence | result | proof |
|---|---|---|
| scoped consumption smoke | `POST_REVIEW_PASS` | inbox/checkpoint = 5/5, state/match/outbox = 0/0/0 |
| expanded consumption smoke | `POST_REVIEW_PASS` | inbox/checkpoint = 50/50, state/match/outbox = 0/0/0 |
| trigger semantic smoke | `POST_REVIEW_PASS` | state/match/outbox = 10/10/10 |
| JSONB serialization fix | `FIX_PASS` | datetime/jsonb path repaired |
| execute runner alignment | `ALIGNMENT_PASS` | scoped DB smoke write path available |
| semantic source selection alignment | `ALIGNMENT_PASS` | oracle-backed source selection produces 10 TriggerMatched |
| N4 unified output run-once oracle | `POST_REVIEW_PASS` | TriggerMatched = 556 |

Boundary proof carried forward:

- N3 outbox status was not updated by the N4 smoke probes.
- N5/N6 refs remained 0 for smoke probes.
- no long-running worker was started.
- no delivery/push/voice/mobile path was touched.
- no sim/position/pnl/real_trade path was touched.
- old system was untouched.

Existing smoke rows now present and must be treated as baseline for future gates:

| smoke run | current purpose | rows |
|---|---|---:|
| `n4_worker_bounded_smoke_20260608_unified_output_probe` | scoped consumption probe | run=1, inbox/checkpoint=5/5 |
| `n4_worker_bounded_smoke_20260608_unified_output_expanded_probe` | expanded consumption probe | run=1, inbox/checkpoint=50/50 |
| `n4_worker_bounded_smoke_20260608_trigger_semantic_probe` | TriggerMatched semantic probe | run=1, state/match/outbox=10/10/10 |

## N4 Remaining Gaps

1. `TriggerPendingMarketData` semantic write path still needs deterministic fixture/oracle coverage.
2. `TriggerStateChanged` semantic write path still needs deterministic fixture/oracle coverage.
3. Duplicate delivery and idempotent replay need bounded stress proof.
4. Retry / partial failure behavior needs bounded proof.
5. Delivered/delivering guard behavior needs explicit rollback/readiness proof before larger runs.
6. Existing smoke rows must be considered non-zero baseline; future runs need distinct run IDs or scoped rollback gates.

Important boundary: the semantic smoke proved 10 oracle-derived `TriggerMatched` rows only. It did not prove that every N4 event type is safe under larger or long-running worker operation.

## N5 Worker Readiness / Gaps

Passed evidence:

- N5 unified output retry run-once is `POST_REVIEW_PASS`.
- deterministic metric join coverage = `556/556`.
- N5 canonical output distribution was written by run-once:
  - `ActionExecuted=7`
  - `ActionBlocked=549`
  - `ActionEligible=0`
  - `ActionSkipped=0`
- N5 HINT source-condition agnostic output spec is `SPEC_PASS`.
- N5 HINT source-condition agnostic spec review is `REVIEW_PASS`.

Remaining gaps:

- N5 worker has not completed scoped consumption smoke.
- N5 worker has not completed expanded consumption smoke.
- N5 worker has not completed semantic action smoke with deterministic N3 metric join.
- N5 outbox consumption remains forbidden until a separate N6/user gate.
- N5 worker rollout must not start from long-running mode; it must start with bounded `max_events`, `max_runtime_seconds`, `stop_file`, and `status_json`.

N5 must continue to obey canonical boundaries:

- consume only N4 standard trigger events.
- create action facts/events only from `TriggerMatched`.
- treat `TriggerPendingMarketData` and `TriggerStateChanged` as no-op / state-gate / quality context, not action confirmation input.
- bind deterministic N3 metric run for action confirmation.
- not trust opaque payload action confirmation.
- not write N6/user projection, sim, voice, mobile, or real trade.

## Recommended Rollout Gate Sequence

### A. N4 Pending / State-Changed Semantic Fixture Smoke

Recommended gate:

`N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE_READINESS_GATE`

Goal:

- provide deterministic fixture/oracle rows for `TriggerPendingMarketData` and `TriggerStateChanged`.
- verify state/outbox write path for both event types.
- prove neither event type writes `common_trigger_match`.
- prove neither event type sets N5 entry.

### B. N4 Idempotency / Duplicate / Retry Bounded Smoke

Recommended gate:

`N4_WORKER_BOUNDED_SMOKE_IDEMPOTENCY_RETRY_CONTRACT_GATE`

Goal:

- duplicate source event replay does not duplicate state/match/outbox.
- existing inbox/checkpoint guards work.
- retry after blocked or partial source selection remains scoped and bounded.

### C. N4 Larger Bounded Smoke

Recommended gates:

- `N4_WORKER_BOUNDED_SMOKE_100_EVENTS_READINESS_GATE`
- `N4_WORKER_BOUNDED_SMOKE_500_EVENTS_READINESS_GATE`

Goal:

- increase scope to 100 then 500 events.
- still no N5.
- still no N3 outbox status update unless a separate consumption policy gate approves it.
- verify runtime and memory behavior without long-running worker.

### D. N4 Worker Rollback Readiness

Recommended gate:

`N4_WORKER_BOUNDED_SMOKE_ROLLBACK_READINESS_GATE`

Goal:

- account for existing scoped, expanded, and semantic smoke rows.
- prove rollback must proceed newest/downstream-safe first.
- block rollback when delivered/delivering, N5/N6/user/sim/order/trade/position refs exist.

### E. N5 Worker Scoped Consumption Smoke

Recommended gate:

`N5_WORKER_BOUNDED_SMOKE_SCOPED_CONSUMPTION_READINESS_GATE`

Goal:

- consume a small bounded set of N4 `TriggerMatched` outbox rows.
- write only N5 inbox/checkpoint in the first smoke if desired.
- keep N5 action facts/events disabled unless semantic action contract is approved.
- no N6 and no N5 outbox consumption.

### F. N5 Semantic Action Smoke With Deterministic N3 Metric Join

Recommended gate:

`N5_WORKER_BOUNDED_SMOKE_SEMANTIC_ACTION_CONTRACT_GATE`

Goal:

- use deterministic N3 action-confirmation metric baseline.
- prove metric join coverage equals selected TriggerMatched count.
- write scoped N5 action facts/events/outbox.
- prove canonical event distribution and HINT trace-only semantics.

### G. N4 -> N5 Chained Bounded Smoke

Recommended gate:

`N4_N5_CHAINED_BOUNDED_SMOKE_READINESS_GATE`

Goal:

- run a bounded N4 event flow followed by bounded N5 consumption.
- still no N6.
- verify idempotency and lineage across N4/N5.
- prove N5 never rewrites N4 state.

### H. N6 Projection Bounded Smoke

Recommended gate:

`N6_PROJECTION_BOUNDED_SHADOW_SMOKE_READINESS_GATE`

Goal:

- consume bounded N5 standard action events.
- write shadow user projection/card only.
- no notification delivery, no push, no voice, no mobile, no sim/order/trade/position.

### I. Long-Running Worker Readiness

Recommended gate:

`N4_N5_N6_LONG_RUNNING_WORKER_READINESS_GATE`

Goal:

- only after bounded gates pass.
- define deployment runbook, stop controls, heartbeats, watermarks, alerting, rollback, and restart behavior.
- still requires explicit final gate before starting any long-running worker.

## Rollback Strategy

Rollback must be reverse-order and scope-first:

1. N6/user projection smoke rows first, if any exist.
2. N5 worker smoke rows next, if any exist.
3. N4 worker smoke rows last.
4. N3 facts/outbox status must be preserved unless a separate N3 rollback gate authorizes changes.
5. N4 oracle lineage and historical run-once evidence must not be mutated by worker smoke rollback.

Every rollback SQL must:

- hard-fail before first executable `DELETE/UPDATE`.
- guard delivered/delivering outbox rows.
- guard downstream N5/N6/user/sim/order/trade/position refs.
- delete only scoped run rows for the exact run ID and consumer name.
- avoid `CASCADE`, `DROP`, and `TRUNCATE`.
- preserve upstream facts and previous lineage.

## Required Safety Rules

- every execute needs contract / preflight / final gate / rollback SQL.
- no long-running worker until explicit final gate.
- no N3 outbox status update unless consumption policy is explicitly approved.
- no N5 outbox consumption unless a separate N6/user gate approves it.
- no N6/voice/mobile/sim/trade without separate layer gate.
- all worker runs must be bounded first: `max_events`, `max_runtime_seconds`, `stop_file`, `status_json`.
- all fixture/oracle semantic smokes must be trace-labeled and must not fabricate market decisions.
- downstream refs require reverse-order rollback review.

## Forbidden Scope Proof

This planning gate did not:

- start worker
- execute N4
- execute N5
- write database
- consume/update outbox/inbox/checkpoint
- enter N6
- trigger delivery/push/voice/mobile
- touch sim/position/pnl/real_trade
- touch proposal/order/trade
- touch old system

## Validation

- source JSON parse: `PASS`
- N4 smoke evidence proof: `PASS`
- N5 run-once evidence proof: `PASS`
- canonical runtime spec boundary review: `PASS`
- planning JSON parse: `PASS`
- `git diff --check`: `PASS`

## Recommended Next Gate

`N4_WORKER_BOUNDED_SMOKE_PENDING_STATE_CHANGED_SEMANTIC_FIXTURE_READINESS_GATE`

