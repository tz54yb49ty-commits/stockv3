# V3 Phase 1 N5 Bounded Action Worker Contract

## Scope

This document defines PR-4 Phase 1 for `scripts/run_n5_bounded_action_worker_once.py`.
PR-4 is wrapper-only: it adds no SQL migration and does not modify execute.py.

Active path:

```text
N4 TriggerMatched
-> scripts/run_n5_bounded_action_worker_once.py
-> scripts/run_action_consumer_once.py --semantic-action-smoke
-> ActionExecuted / ActionBlocked / ActionSkipped
```

Phase 1 forbids `ActionEligible` output, N5 outbox consumption, N6 execution,
real trade, sim, voice, mobile, position writes, and order writes.

## Explicit Lineage

Every execute attempt must pass explicit lineage:

```text
for_trade_date
source_trigger_run_id
source_metric_run_id
projection_run_id
action_run_id
consumer_name
source_event_type=TriggerMatched
```

`source_metric_run_id` must equal `projection_run_id`.
Any missing value, implicit selector, mismatch, or non-`TriggerMatched` event type
blocks before the child starts.

## Pre-Child Fail-Closed Gates

The wrapper must block with `result=BLOCKED`, `exit=2`, `child_invoked=false`,
and zero action/fact/event/outbox/inbox/checkpoint/tracking writes for:

```text
missing or inconsistent lineage
consumer inbox/checkpoint already exists for candidate rows
candidate_total > max_events
trade_date proof missing or mismatched
metric_missing or duplicate metric join
stale TriggerMatched
ActionEligible preflight count > 0
```

`max_events` is a child safety limit only after an authoritative count proves
`candidate_total <= max_events`. It must not silently consume the first N rows.

## Stale TriggerMatched Policy

Stale `TriggerMatched` is technical `BLOCKED` in Phase 1. The wrapper must not
generate `ActionSkipped(expired)` for stale events. The stale proof requires:

```text
common_trigger_state.run_id = source_trigger_run_id
common_trigger_state.current_status = matched
common_trigger_state.last_trigger_match_id = candidate trigger_match_id
```

Missing proof blocks.

## Rollback Contract

The wrapper generates the final rollback SQL. The child rollback artifact is not
the authoritative rollback for PR-4.

The final rollback covers only:

```text
common_action_tracking_state by action_run_id with source_trigger_run_id guard
stock/index/board action facts by action_run_id
common_action_event by action_run_id
N5 common_event_outbox and common_event_ledger by source_layer=N5_action and source_run_id=action_run_id
delivery attempts for scoped N5 events
N4 consumer inbox exact candidate event ids for this consumer
N4 consumer checkpoint rows whose checkpoint_payload action_run_id matches
common_action_quality_item and common_action_run by action_run_id
```

Rollback must block if scoped N5 outbox rows are delivered/delivering, if
downstream inbox/checkpoint refs exist, or if user/N6/sim/voice/mobile/position/order
refs contain the scoped action or source trigger run ids.

Rollback must not delete N3 facts, N4 trigger facts, N4 outbox rows, N6/user
projection rows, voice rows, sim rows, mobile rows, position rows, order rows,
or real-trade rows.

## Runtime Result Contract

```text
plan-only => NOOP
singleton conflict => NOOP
stop before child => NOOP
preflight fail => BLOCKED
child timeout => UNKNOWN_AFTER_TIMEOUT
child exit 1 + rolled_back post-check => CRASHED
unresolved post-check => COMMIT_UNKNOWN
rollback manifest incomplete after commit evidence => COMMIT_UNKNOWN
all valid and ActionEligible=0 => PASS
```

N5 is single-transaction in Phase 1. The wrapper does not use `PARTIAL`.

## Manifest Contract

Status and manifest must include:

```text
invocation_id
wrapper_run_id
action_run_id
source_trigger_run_id
source_metric_run_id
projection_run_id
candidate_total
max_events
trade_date_proof
metric_preflight
stale_trigger_preflight
action_event_counts
ActionEligible=0 proof
rollback_sql_path/hash
tracking_state_rollback_coverage
external side effects all zero
downstream_consumption_allowed=false
```

## Old Entrypoint Warning

`scripts/run_action_consumer_once.py` is an existing child-capable N5 entrypoint,
but it does not own the PR-4 global bounded worker lock, authoritative total
preflight, stale-trigger preflight, metric-missing fail-closed behavior, or
wrapper-level rollback supplement.

Old/direct N5 entrypoints, including direct `scripts/run_action_consumer_once.py`,
can bypass the Phase 1 shared global lock. Operational runbooks must treat direct
use of `scripts/run_action_consumer_once.py` as a bounded-lock bypass for PR-4.
The Phase 1 runbook must forbid old N5 entries from running in parallel with the
bounded wrapper. PR-4 runs must enter through
`scripts/run_n5_bounded_action_worker_once.py`.
