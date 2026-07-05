# N4 / N5 Open Startup And Final Shape Implementation

Result: `IMPLEMENTATION_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-11T02:34:08+08:00`

## Summary

The N4/N5 open-startup plan is now registered as the current runtime rollout shape.

N4/N5 must not start as long-running workers. The required path is:

```text
run-once -> bounded smoke -> scheduler bounded run-once -> long-running worker readiness
```

N4 must wait for N3 B1/C1/B2 auto-poll to produce at least one effective closed-minute execution. N5 must wait for compliant N4 `TriggerMatched` events.

## Current N3 Prerequisite

Current wrapper report: `docs/N3_INTRADAY_B1_C1_B2_AUTO_POLL_REPORT_20260611.json`

```text
status=noop
reason=no_closed_minute_available
latest_closed_minute=null
latest_closed_minute_hhmm=null
executed_child_command_count=0
b1_c1_b2_executed=false
```

Therefore N4 readiness is not allowed yet for `20260611`.

## N4 Startup Shape

Prerequisites:

- N3 B1/C1/B2 has at least one effective closed-minute execution.
- N4 context localization is complete for the current N2 condition run and N3 lineage.
- rollback/readiness scope is regenerated for exact `20260611` run IDs.

Sequence:

```text
N4 run-once dry-run/preflight/final gate/execute/post-review
-> N4 bounded worker smoke
-> N4 scheduler bounded run-once
-> long-running N4 worker readiness/final gate
```

N4 may consume only N3 standard events, approved N3 standardized realtime projection facts, and localized N4 trigger context snapshots.

N4 must not pull market data, recompute N2, scan N3 raw facts as an event substitute, read N5/N6 facts, or touch the old system.

N4 output boundary:

| event | common_trigger_match | N5 entry |
|---|---:|---:|
| `TriggerMatched` | yes | yes |
| `TriggerPendingMarketData` | no | no |
| `TriggerStateChanged` | no | no |

N4 must not update N3 outbox status. It maintains its own N4 inbox/checkpoint.

## N5 Startup Shape

Prerequisites:

- N4 has produced compliant `TriggerMatched` events.
- N5 deterministic N3 action-confirmation metric join is ready.
- N5 scoped worker smoke contract/preflight/rollback is approved.

Sequence:

```text
N5 run-once dry-run/preflight/final gate/execute/post-review
-> N5 bounded worker smoke
-> N5 scheduler bounded run-once
-> long-running N5 worker readiness/final gate
```

N5 input boundary:

| N4 event | N5 action confirmation |
|---|---|
| `TriggerMatched` | only positive entry |
| `TriggerPendingMarketData` | no action confirmation |
| `TriggerStateChanged` | state gate only, no new action confirmation |

N5 canonical outputs:

```text
ActionEligible
ActionBlocked
ActionExecuted
ActionSkipped
```

`ActionExecuted` means only that an N5 action confirmation fact was established and a canonical action event was emitted. It does not mean real order, sim trade, N6 card, voice, mobile push, or trade intent.

## Final Shape

N4 final worker:

- consumes N3 standard events/projection facts
- writes trigger facts, N4 outbox, N4 inbox/checkpoint in one transaction
- owns trigger state/outcome only

N5 final worker:

- consumes N4 standard events
- starts action confirmation only from `TriggerMatched`
- writes action facts, N5 outbox, N5 inbox/checkpoint in one transaction
- owns action confirmation only

N6 remains the first layer that may decide user-facing display, notification, voice, mobile, sim, position, or trade intent.

## Test Mapping

- N4 state transition and idempotency: `tests/test_n4_worker_state_transition.py`
- N5 event boundary and action semantics: `tests/test_action_dry_run.py`
- N5 event schema contract: `tests/test_action_schema_event_review.py`

## Forbidden Scope Proof

This gate did not execute N4 or N5, did not start any worker, did not write the database, did not execute rollback SQL, did not consume or update outbox/inbox/checkpoint, did not update N3 outbox status, did not enter N6, did not touch delivery/push/voice/mobile, did not touch proposal/order/trade, did not touch sim/position/PnL/real trade, and did not touch the old system.

## Validation

- JSON parse: `PASS`
- Targeted tests: `37 OK`
- Command: `PYTHONPATH=src python3 -m unittest tests.test_n4_worker_state_transition tests.test_action_dry_run tests.test_action_schema_event_review`
- `git diff --check`: `PASS`

## Next Recommended Gate

`N3_INTRADAY_B1_C1_B2_AUTO_POLL_FIRST_EFFECTIVE_EXECUTION_OBSERVATION_AND_CLOSEOUT`
