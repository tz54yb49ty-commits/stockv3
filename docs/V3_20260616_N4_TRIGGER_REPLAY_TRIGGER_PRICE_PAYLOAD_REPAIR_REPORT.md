# V3 20260616 N4 Trigger Replay Trigger Price Payload Repair Report

Result: `REPAIR_PASS`

## Scope

This gate repaired only N4 action-confirmation metric replay payload/fact mapping, tests, and this report. It did not execute N4 replay, write business database rows, consume outbox/inbox/checkpoint, or enter N5/N6.

## Root Cause

The blocked run `v3_n4_trigger_replay_20260616_until_1401_v1` produced `TriggerMatched=540`, but all 540 matched rows missed canonical trigger price fields:

- `common_trigger_match.trigger_price IS NULL=540`
- `common_trigger_match.raw_json.trigger_price missing=540`
- `common_event_outbox.payload_json.trigger_price missing=540`
- `metric_trace.current_price present=540`

The cause was local to N4 mapping: action-confirmation metric plans kept `metric_trace.current_price` but did not promote it to top-level `plan.trigger_price`, and the execute event envelope did not copy it into `payload_json`. The standard match writer already reads `plan.trigger_price` for both the physical column and raw_json.

## Code Repair Summary

- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
  - `TriggerMatched` plans now set `trigger_price` from N3 metric `current_price`.
  - `trigger_price_source` is fixed to `n3_action_confirmation_metric.current_price`.
- `src/ashare_v3/trigger/action_confirmation_metric_execute.py`
  - outbox payload now includes `trigger_price` and `trigger_price_source`.
- Tests now prove:
  - matcher plans include canonical `trigger_price`;
  - execute envelope includes `trigger_price`;
  - common_trigger_match insert params receive `trigger_price`;
  - match raw_json canonical plan includes `trigger_price_source`.

## Trigger Price Mapping Proof

Canonical mapping after this repair:

```text
N3 metric current_price
  -> N4 plan.trigger_price
  -> common_trigger_match.trigger_price
  -> common_trigger_match.raw_json.trigger_price
  -> common_event_outbox.payload_json.trigger_price
```

Source marker:

```text
trigger_price_source = n3_action_confirmation_metric.current_price
```

## Pending Non-Entry Regression Proof

`TriggerPendingMarketData` behavior is unchanged:

- does not write `common_trigger_match`;
- is not an N5 action entry;
- has `n5_entry_allowed=false`;
- remains state/outbox only.

## Validation

Passed:

```text
PYTHONPATH=src:scripts python3 -m unittest tests.test_trigger_action_confirmation_metric_matcher tests.test_trigger_action_confirmation_metric_execute
48 tests OK

python3 -m compileall src/ashare_v3/trigger tests/test_trigger_action_confirmation_metric_matcher.py tests/test_trigger_action_confirmation_metric_execute.py
PASS

PYTHONPATH=src python3 scripts/check_n4_contract.py
PASS

rollback static check for sql/V3_20260616_n4_trigger_replay_rollback.sql
PASS
```

Additional validation:

```text
python3 -m json.tool docs/V3_20260616_N4_TRIGGER_REPLAY_TRIGGER_PRICE_PAYLOAD_REPAIR_REPORT.json >/dev/null
PASS

git diff --check
PASS
```

## Forbidden Scope Proof

- N4 replay executed: false
- database written: false
- rollback SQL executed: false
- N3 metric modified: false
- outbox/inbox/checkpoint consumed or updated: false
- N5 entered: false
- N6 entered: false
- worker/scheduler started: false
- voice/mobile/sim/position/order/real_trade touched: false
- old system touched: false

## Next Gate

Allowed: rollback / regenerated replay gate.

Existing blocked run evidence must not be silently rewritten. A scoped rollback or regenerated replay is required before N5 readiness.
