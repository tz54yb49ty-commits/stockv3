# N4/N5 Canonical Runtime Contract Alignment Readiness

Gate: `N4_N5_CANONICAL_RUNTIME_CONTRACT_ALIGNMENT_READINESS_GATE`

Layer role: `runtime_control`

Result: `BLOCKED`

This is a read-only readiness review after `N3_N4_N5_RUNTIME_TERMINOLOGY_AND_RESPONSIBILITY_FREEZE_GATE = FREEZE_PASS`. It did not execute N4/N5, write the database, consume or update outbox/inbox/checkpoint, start a worker, enter N6, touch voice/mobile/sim/position/PnL/real trade, modify a scheduler, or execute rollback.

## Canonical Authority Proof

The freeze registry parses successfully and fixes this authority order:

```text
docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md
docs/V3_N3_N4_N5_ACTION_CONFIRMATION_RULE_SPEC.md
docs/N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md
docs/N5_CANONICAL_ACTION_FLOW_v0.1.md
```

Frozen runtime terms:

```text
runtime signal_type = B_BUY / S_SELL only
N4 events = TriggerMatched / TriggerPendingMarketData / TriggerStateChanged
N5 events = ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped
BUY_HINT / SELL_HINT = condition provenance, not runtime signal_type
ActionEvent / HintEvent / RiskEvent / PositionEvent = historical/superseded
TriggerCleared = historical/superseded
```

## Findings

### N4

N4 has strong canonical evidence:

```text
src/ashare_v3/events/models.py defines canonical N4_EVENT_TYPES.
src/ashare_v3/trigger/standard_trigger_execute.py uses TriggerMatched / TriggerPendingMarketData / TriggerStateChanged.
scripts/check_n4_contract.py returned passed=true, finding_count=0.
```

Residual N4 caveat:

```text
src/ashare_v3/trigger/projection_matcher.py still uses B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT as internal projection candidate selectors before canonicalizing output to B_BUY / S_SELL plus trigger_mark_candidate.
Older local/synthetic/C3 replay paths still contain legacy signal candidate language.
```

Decision: this is not an immediate N4 output-contract blocker if persisted outputs remain canonical, but it requires a dedicated compatibility review before canonical closeout.

### N5

N5 has partial canonical evidence:

```text
src/ashare_v3/events/models.py defines canonical N5_EVENT_TYPES.
src/ashare_v3/action/event_factory.py validates N5 event type through validate_n5_event_type.
src/ashare_v3/action/dry_run.py defines ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped.
src/ashare_v3/action/execute.py blocks deprecated ActionEvent / HintEvent / RiskEvent / PositionEvent output planning.
```

N5 remains blocked:

```text
scripts/review_action_schema_event_contract.py exit code = 2
p0_count = 2
missing canonical literals / fields =
  TriggerStateChanged
  ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped
  source_trigger_state_id
  original_condition_key
  action_state
  confirmation_status
  action_policy
  trace_json
```

Additional N5 caveat:

```text
src/ashare_v3/action/preflight.py
src/ashare_v3/action/run_once_dry_run.py
src/ashare_v3/action/consumer_dry_run.py
scripts/plan_action_consumer_run_once_dry_run.py
```

still describe `TriggerCleared` as a standard/current N5 input in summaries or quality messages. That conflicts with the freeze, where `TriggerCleared` is historical/superseded and clearing is represented as `TriggerStateChanged(trigger_live=false)`.

## Decision

`BLOCKED`

Do not proceed to N4/N5 production readiness or execute gates from this review. The freeze is complete, but N5 canonical schema/event contract alignment has P0 blockers.

## Recommended Gate Order

1. `N5_CANONICAL_SCHEMA_EVENT_CONTRACT_ALIGNMENT_GATE`
2. `N5_TRIGGERCLEARED_INPUT_SUPERSESSION_ALIGNMENT_GATE`
3. `N4_PROJECTION_MATCHER_LEGACY_SIGNAL_COMPATIBILITY_REVIEW_GATE`
4. `N4_N5_CANONICAL_RUNTIME_STATIC_GUARD_EXPANSION_GATE`
5. `N4_N5_PRODUCTION_CHAIN_READINESS_REFRESH_AFTER_CANONICAL_ALIGNMENT`

## Forbidden Scope Proof

```text
n4_executed=false
n5_executed=false
database_written=false
outbox_inbox_checkpoint_consumed_or_updated=false
worker_started=false
n6_entered=false
voice_mobile_sim_position_pnl_real_trade_touched=false
scheduler_modified=false
rollback_executed=false
```

Next recommended gate:

```text
N5_CANONICAL_SCHEMA_EVENT_CONTRACT_ALIGNMENT_GATE
```
