# N5 Action Event HINT 30m Passthrough Contract Repair

Result: `CONTRACT_PASS`

Gate: `N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_CONTRACT_REPAIR_GATE`

Layer role: `runtime_control`

This gate only defines the repair contract and validation plan. It did not modify code, execute N5, write the database, consume or update N4 outbox/inbox/checkpoint, enter N6, start a worker, or execute rollback SQL.

## Root Cause Summary

The failed N5 retry execute reached the runner but failed before commit:

- exception: `EventContractError`
- blocker: `n5_event_contract_rejects_30m_trigger_period_passthrough`
- failure stage: `build_n5_action_event -> validate_n5_trigger_fact_passthrough_payload`
- transaction committed: `false`
- target N5 scoped rows: all `0`

N4 source payload is legal. The N4 post-review and failure review prove HINT `TriggerMatched` rows use:

```json
{
  "trigger_kind": "hint",
  "condition_key": "BUY_HINT or SELL_HINT",
  "trigger_period": "30m",
  "triggered_periods": [],
  "all_trigger_periods": [],
  "primary_trigger_period": null,
  "trigger_price": "present",
  "n5_entry_allowed": true
}
```

The N5 shared validation guard is also correct: legal HINT 30m is accepted only when formal period fields are empty, and any `30m` inside `triggered_periods / all_trigger_periods / primary_trigger_period` remains invalid.

The bug is in `src/ashare_v3/action/execute.py::build_action_event_passthrough_payload`: it currently reconstructs `primary_trigger_period` from `trigger_period` when the primary period is empty. For legal HINT 30m, this turns `primary_trigger_period=null` into `primary_trigger_period=30m`, causing the contract error.

## Approved Repair Scope

Allowed files:

- `src/ashare_v3/action/execute.py`
- `src/ashare_v3/action/event_factory.py`, only if needed for narrow payload handoff validation
- `tests/test_action_execute.py`
- related N5 event/model tests only if needed

Forbidden scope:

- Do not modify N4 matcher semantics.
- Do not relax `src/ashare_v3/events/models.py` to allow `30m` in formal period fields.
- Do not mutate N4/N3/N2/N1 facts or contracts.
- Do not execute N5.
- Do not consume or update N4 outbox/inbox/checkpoint.
- Do not enter N6.

## Required Code/Test Changes

Primary implementation rule:

`primary_trigger_period` must come only from explicit formal primary fields. Do not derive it from `trigger_period`.

HINT 30m passthrough must preserve:

- `trigger_period=30m`
- `triggered_periods=[]`
- `all_trigger_periods=[]`
- `primary_trigger_period=null`
- `trigger_kind=hint`
- `condition_key/original_condition_key=BUY_HINT or SELL_HINT`

`baseline_source` must not depend on forcing `primary_trigger_period=30m`. It may use explicit `period_trigger_baseline_trace.baseline_source` or another existing trace fallback, but it must not encode `30m` into formal period fields.

Ordinary trigger rules remain:

- `trigger_kind=trigger + trigger_period=30m` must continue to `BLOCK`.
- formal trigger periods must remain only `Y/Q/M/W/D`.
- `30m` inside `triggered_periods / all_trigger_periods / primary_trigger_period` must continue to `BLOCK`.

`TriggerPendingMarketData` remains:

- quality-only / no-op
- no action fact
- no common action event
- no N5 outbox

## Regression Plan

Add or confirm these tests:

- `tests/test_action_execute.py::test_action_event_passthrough_payload_preserves_buy_hint_30m_empty_formal_periods`
- `tests/test_action_execute.py::test_action_event_passthrough_payload_preserves_sell_hint_30m_empty_formal_periods`
- `tests/test_action_execute.py` or related N5 event tests: legal HINT 30m `build_n5_action_event` does not raise `EventContractError`
- related N5 event tests: ordinary `trigger_kind=trigger + trigger_period=30m` raises `EventContractError`
- related N5 event tests: `30m` inside `triggered_periods / all_trigger_periods / primary_trigger_period` raises `EventContractError`
- `tests/test_action_execute.py::test_trigger_pending_market_data_remains_quality_only_no_action_event`

## Acceptance Criteria

- Failure reproducer is covered by unit test.
- Legal HINT 30m N5 event payload contains:
  - `trigger_period=30m`
  - `triggered_periods=[]`
  - `all_trigger_periods=[]`
  - `primary_trigger_period=null`
- Legal HINT 30m no longer raises `EventContractError`.
- Ordinary `trigger_kind=trigger + trigger_period=30m` remains rejected.
- Any `30m` inside formal period fields remains rejected.
- `TriggerPendingMarketData` does not generate action output.
- No N5 execute and no DB writes occur in this contract gate.

## Validation Plan

Run after implementation:

```bash
PYTHONPATH=src python3 -m unittest tests/test_action_execute.py
PYTHONPATH=src python3 -m unittest tests/test_n4_v4_enforcement.py
PYTHONPATH=src python3 -m unittest tests/test_trigger_projection_matcher_execute.py
python3 -m compileall src/ashare_v3/action src/ashare_v3/events tests
python3 -m json.tool docs/N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_CONTRACT_REPAIR.json >/dev/null
git diff --check
```

## Forbidden Scope Proof

- N5 execute: `false`
- DB write: `false`
- action fact/event/outbox write: `false`
- N4 outbox consume/update: `false`
- N5 inbox/checkpoint write: `false`
- N6 entered: `false`
- worker started: `false`
- rollback SQL executed: `false`
- delivery/push/voice/mobile: `false`
- sim/position/PnL/real trade: `false`
- proposal/order/trade: `false`
- old system touched: `false`
- code modified in this gate: `false`

## Next Gate

`N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_GATE`
