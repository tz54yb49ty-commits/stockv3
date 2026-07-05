# N4 Worker Bounded Smoke Trigger Semantic Runner Alignment Report

Result: `ALIGNMENT_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_RUNNER_ALIGNMENT_GATE`

Layer role: `N4_trigger`

## Root Cause

The bounded worker smoke helper already supported `evaluations` and `previous_states`, but the CLI execute path always called it with:

```text
evaluations=[]
previous_states={}
```

That made consumption-only smoke work, but blocked future trigger-semantic smoke from generating transition plans through a deterministic fixture or oracle.

## Code Repair Summary

Updated:

- `scripts/run_n4_worker_bounded_smoke_once.py`
- `src/ashare_v3/trigger/worker_consumer.py`
- `tests/test_n4_worker_bounded_smoke.py`

Added semantic runner inputs:

- `--semantic-smoke`
- `--semantic-fixture-path`
- `--semantic-oracle-run-id`

Added helper functions:

- `require_semantic_inputs`
- `load_semantic_fixture`
- `load_semantic_oracle_evaluations`

Consumption-only mode remains unchanged. Semantic mode loads fixture/oracle `evaluations` and `previous_states` before calling `build_worker_smoke_plan`.

## Runner Semantic Mode Proof

- Fixture/oracle supplied without `--semantic-smoke` blocks before DB connect/write.
- `--semantic-smoke` without fixture/oracle blocks before DB connect/write.
- Execute still requires `--execute --user-confirmed --smoke-run-id`.
- Baseline dirty guard remains active.
- `max_events` guard remains active.
- Fixture evaluations can generate `TriggerMatched + TriggerStateChanged` transition plans.

## Oracle / Fixture Safety Proof

Fixture/oracle-derived plans are tagged:

- `fixture_only=true`
- `source_oracle_run_id`
- `not_new_market_decision=true`

The oracle path is read-only and selects from existing N4 outbox rows. It does not mutate oracle facts/outbox and does not update N3 outbox status.

## Event Persistence Proof

`TriggerMatched` semantic plans write:

- `common_trigger_state`
- `common_trigger_match`
- `common_event_outbox`
- `n5_entry_allowed=true`

`TriggerPendingMarketData` and `TriggerStateChanged` semantic plans write state/outbox only:

- `common_trigger_match=false`
- `n5_entry_allowed=false`

## Forbidden Scope Proof

This gate did not:

- execute smoke
- write database
- consume/update N3 outbox
- enter N5/N6
- start worker
- delivery/push/voice/mobile
- sim/position/pnl/real_trade
- proposal/order/trade
- touch old system

## Validation

- targeted worker tests: `23 tests OK`
- trigger test group: `128 tests OK`
- compileall: `PASS`
- check_n4_contract.py: `PASS`
- CLI help exposes semantic flags: `PASS`
- report JSON parse: `PASS`
- git diff --check: `PASS`

## Next Gate

`N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_READINESS_GATE`
