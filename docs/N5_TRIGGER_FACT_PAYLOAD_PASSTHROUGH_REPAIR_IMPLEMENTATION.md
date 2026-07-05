# N5 Trigger Fact Payload Passthrough Repair Implementation

Status: IMPLEMENTATION_PASS

Layer role: N5_action

Scope: forward code fix and regression tests only.

This gate did not write database rows, did not update historical payloads, did not consume outbox, did not run N4/N5/N6, did not start workers, and did not touch N6 projection/UI, delivery, push, voice, mobile, sim, position, pnl, proposal, order, or real trade.

## Implemented Forward Fix

Future N5 `ActionExecuted` and `ActionBlocked` event payloads now carry N4 actual trigger facts through the N5 action event/outbox payload path.

Required passthrough fields:

```text
n4_trigger_event_id
trigger_price
trigger_period
triggered_periods
all_trigger_periods
primary_trigger_period
trigger_kind
period_trigger_baseline_trace
baseline_source
```

## Source Of Truth

The forward fix builds payload passthrough from the N5 action plan row, which is derived from N4 `TriggerMatched` payload and persisted into the N5 action fact:

```text
source_payload_json.trigger_price
source_payload_json.triggered_periods
source_payload_json.all_trigger_periods
source_payload_json.primary_trigger_period
source_payload_json.trigger_kind
source_market_trace.period_trigger_baseline_trace
```

`baseline_source` is resolved for the actual `primary_trigger_period` from:

```text
period_trigger_baseline_trace.traced_periods[primary_trigger_period].baseline_source
```

The implementation does not infer actual triggered periods from `condition_key` or `required_periods`, does not trust opaque `payload.action_confirmation`, does not read raw K, and does not pull realtime quotes.

## Modified Files

```text
src/ashare_v3/action/execute.py
src/ashare_v3/action/event_factory.py
src/ashare_v3/events/models.py
tests/test_action_execute.py
tests/test_action_event_contract.py
docs/N5_TRIGGER_FACT_PAYLOAD_PASSTHROUGH_REPAIR_IMPLEMENTATION.md
docs/N5_TRIGGER_FACT_PAYLOAD_PASSTHROUGH_REPAIR_IMPLEMENTATION.json
```

## Code Changes

`src/ashare_v3/action/execute.py`:

```text
Added build_action_event_passthrough_payload(...)
Added resolve_baseline_source_for_period(...)
insert_action_facts_and_events(...) now passes the enriched payload into build_n5_action_event(...)
```

`src/ashare_v3/action/event_factory.py`:

```text
build_n5_action_event(...) now carries n4_trigger_event_id, defaulting to source_trigger_event_id when not explicitly supplied.
All passthrough payload keys supplied by execute.py are preserved.
```

`src/ashare_v3/events/models.py`:

```text
Added N5_TRIGGER_FACT_PASSTHROUGH_PAYLOAD_KEYS.
ActionExecuted and ActionBlocked now require trigger fact passthrough payload fields.
```

## Regression Tests

Added tests for:

```text
execute payload builder carries n4_trigger_event_id
execute payload builder carries trigger_price
execute payload builder carries triggered_periods
execute payload builder carries all_trigger_periods
execute payload builder carries primary_trigger_period
execute payload builder carries trigger_kind
execute payload builder carries period_trigger_baseline_trace
execute payload builder resolves baseline_source for actual primary_trigger_period
ActionBlocked rejects missing trigger fact passthrough payload
ActionExecuted preserves trigger fact passthrough payload
```

## Historical Payload Repair

Historical payload repair was not performed in this gate.

Still requires a separate scoped repair gate with rollback:

```text
UPDATE common_action_event.payload_json
UPDATE common_event_outbox.payload_json for source_layer=N5_action and scoped action_run_id
repair N6 projection/card only if downstream materialization exists and is explicitly authorized
```

## Validation

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_execute.py' => 21 tests OK
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_event_contract.py' => 5 tests OK
JSON parse => passed
python3 -m compileall scripts src tests => passed
git diff --check => passed
```

## Gate Result

```text
IMPLEMENTATION_PASS
allow_historical_repair_gate=true
allow_n5_forward_execute_preflight_refresh=true
```
