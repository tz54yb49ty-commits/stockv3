# N5 Trigger Fact Payload Passthrough Repair Contract

Status: CONTRACT_PASS

Generated at: 2026-06-06T05:17:54.152174+00:00

Layer role: N5_action

Scope: contract and dry-run only. This gate does not write database rows, does not rerun N5, does not consume or update outbox, does not enter N6, does not start workers, and does not touch delivery/push/voice/mobile/sim/position/pnl/real trade/proposal/order/trade.

## Root Cause

`src/ashare_v3/action/execute.py` builds N5 action event payloads with only:

```text
source_action_fact_table
source_action_fact_id
action_key
blocked_reason
```

`src/ashare_v3/action/event_factory.py` enriches generic N5 context and `trigger_period`, but it does not copy actual N4 trigger facts:

```text
trigger_price
triggered_periods
all_trigger_periods
primary_trigger_period
trigger_kind
period_trigger_baseline_trace
baseline_source
```

The N5 action fact already has the required actual trigger facts, and its price/period matches N4 actual trigger facts.

## Payload Contract

For future canonical N5 `ActionExecuted` and `ActionBlocked`, payload must include:

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

`n4_trigger_event_id` must equal the N4 `TriggerMatched` event id and may also match `source_trigger_event_id` for compatibility.

## Source Priority

Source of truth is the N5 action fact joined to the N4 `TriggerMatched` fact/outbox payload:

```text
1. N5 action fact joined to N4 TriggerMatched fact/outbox payload
2. N5 action fact source_payload_json copied from N4 TriggerMatched payload
3. N5 action fact source_market_trace.period_trigger_baseline_trace copied from N4 payload
```

N5 must not infer actual periods from `condition_key` or `required_periods`, must not trust opaque `payload.action_confirmation`, must not pull raw K, and must not pull realtime quotes.

## Sample Expected Result

Sample N4 trigger event:

```text
evt_61bf1423e33a28d3e19c879c71a8d24a5241bc16
asset=stock:SH:688690
```

Expected passthrough:

```text
trigger_price=43.73
triggered_periods=["D"]
all_trigger_periods=["D"]
primary_trigger_period=D
trigger_period=D
baseline_source=trigger_baseline
```

Sample proof is stored in `docs/N5_TRIGGER_FACT_PAYLOAD_PASSTHROUGH_REPAIR_CONTRACT.json` under `sample.proof`.

## Forward Fix Scope

Forward fix belongs to the next implementation gate:

```text
src/ashare_v3/action/execute.py
src/ashare_v3/action/event_factory.py
tests/test_action_execute.py
tests/test_action_event_contract.py or equivalent N5 tests
```

Implementation must make future N5 action event and N5 outbox payloads carry the full trigger facts without repairing historical rows in this gate.

## Historical Display Repair Scope

Historical display repair is explicitly not executed in this gate. A later scoped repair gate must separately update, with rollback:

```text
common_action_event.payload_json
common_event_outbox.payload_json for source_layer=N5_action and this action_run_id
N6 projection/card if already materialized from deficient payload
```

Rollback must be scoped by action_run_id, source_trigger_run_id, and N5 event/source_trigger_event_id, and must guard downstream refs.

## Gate Result

```text
CONTRACT_PASS
allow_implementation_gate=true
```
## Validation

```text
JSON parse=passed
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_execute.py' => 20 tests OK
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action_event_contract.py' => 4 tests OK
event_factory_passthrough_when_payload_supplied=PASS
execute_payload_builder_root_cause_static_assertion=PASS
python3 -m compileall scripts src tests=passed
git diff --check=passed
new forward-fix regression tests=planned in implementation gate
```

