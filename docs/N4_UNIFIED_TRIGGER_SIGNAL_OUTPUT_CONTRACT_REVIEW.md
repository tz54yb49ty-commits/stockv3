# N4 Unified Trigger Signal Output Contract Review

Result: **REVIEW_PASS**

Layer role: `runtime_control`

Generated at: `2026-06-09T20:18:30+08:00`

This gate reviewed the N4 unified trigger signal output proposal only. It did not execute N4, did not write database rows, did not consume or update outbox/inbox/checkpoint, did not enter N5/N6, and did not start workers.

## Review Inputs

- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.md`
- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.json`
- `docs/N4_TRIGGER_RULE_SPEC_v4.md`
- `docs/N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`
- `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`
- `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`
- `AGENTS.md`

## Approved Decisions

Runtime_control approves the three-layer signal model:

```text
signal_type:
  runtime direction only: B_BUY / S_SELL

condition_signal_type:
  condition family: BUY / SELL / BUY:FULL / SELL:FULL / BUY_HINT / SELL_HINT

condition_key / original_condition_key:
  original N2 condition provenance and trace
```

Runtime_control approves one consistent N4 payload envelope for all six condition families:

```text
BUY
SELL
BUY:FULL
SELL:FULL
BUY_HINT
SELL_HINT
```

Runtime_control approves carrying the 30m marker fields on every N4 output payload, including non-30m families, so later N5/N6 gates do not infer 30m semantics from `condition_key`.

Runtime_control approves the corrected HINT semantics:

```text
BUY_HINT / SELL_HINT:
  trigger_kind=hint
  trigger_period=30m may be valid for TriggerMatched
  triggered_periods=[]
  all_trigger_periods=[]
  primary_trigger_period=null
  projection_period=30m
  projection_30m_type=volume_up / shrink_down
```

Runtime_control confirms that `30m` must still be forbidden in:

```text
triggered_periods
all_trigger_periods
primary_trigger_period
```

Runtime_control approves the ordinary and FULL formal-period boundary:

```text
ordinary BUY/SELL/FULL:
  trigger_kind=trigger
  trigger_period in Y/Q/M/W/D only
  triggered_periods/all_trigger_periods/primary_trigger_period in Y/Q/M/W/D only
```

Runtime_control approves payload-only first. Physical schema migration is deferred to a dedicated schema impact gate.

## Approved Field Names

Approved canonical N4 payload field names:

```text
signal_type
runtime_signal_type
direction
condition_signal_type
condition_key
original_condition_key
trigger_kind
trigger_mark_candidate
requested_periods
triggered_periods
all_trigger_periods
primary_trigger_period
triggered_period_details
trigger_period
trigger_price
trigger_time
event_time
price_source
match_basis
baseline_source
projection_30m_required
projection_30m_flag
projection_30m_type
projection_period
projection_30m_volume_up_flag
projection_30m_shrink_down_flag
trigger_live
current_status
n5_entry_allowed
data_quality_status
```

`runtime_signal_type` is approved as a readability alias. If emitted, it must equal `signal_type`.

## Required Changes Before N4 Code Alignment

The proposal direction is approved, with these required changes:

1. Add `triggered_period_details` to `required_unified_fields` in the proposal-derived contract artifacts. The proposal markdown requires it, but the current proposal JSON list omits it.
2. Treat `triggered_period_details` as required and non-empty for formal matched `trigger_kind=trigger` rows where one or more formal periods fired.
3. For HINT matched rows, require the `triggered_period_details` field to exist as an empty object or empty list; 30m projection details must remain in projection trace fields, not formal period details.
4. Ensure `condition_signal_type` is derived from N2 condition provenance and never from runtime `signal_type` alone.
5. Ensure N4 payload never emits final `action_mark`; N4 may only emit `trigger_mark_candidate`.
6. Keep all changes N4-scoped through the next schema/code dry-run alignment gates. N5/N6 changes are follow-up requirements only.

## Payload-Only vs Schema Migration Decision

Decision: **payload-only first**.

Approved first landing target:

```text
common_event_outbox.payload_json
common_trigger_match raw/payload JSON where available
common_trigger_state raw/payload JSON where available
dry-run / preflight / execute report JSON
```

Schema migration is not approved in this review gate. The next schema impact gate may propose additive columns for selected high-value fields, but that must be separately reviewed.

## P0 Guard List

Future N4 dry-run/preflight/final gate must P0 block on:

```text
signal_type not in B_BUY/S_SELL
runtime_signal_type present and not equal to signal_type
condition_signal_type missing or not in BUY/SELL/BUY:FULL/SELL:FULL/BUY_HINT/SELL_HINT
condition_key missing
original_condition_key missing
condition_signal_type inconsistent with condition_key family
trigger_kind missing or invalid
TriggerMatched trigger_price missing
TriggerMatched n5_entry_allowed missing or false
formal matched row missing requested_periods
formal matched row missing triggered_periods
formal matched row missing all_trigger_periods
formal matched row missing primary_trigger_period
formal matched row missing non-empty triggered_period_details
30m in triggered_periods
30m in all_trigger_periods
30m in primary_trigger_period
ordinary BUY/SELL with trigger_period=30m
FULL with trigger_period other than D
FULL without N2 FULL context proof
FULL with trigger_kind=hint
FULL with trigger_mark_candidate=30m_volume/30m_shrink
FULL with any 30m formal-period marker
HINT matched with trigger_period other than 30m
HINT matched without projection_30m_required=true
HINT matched without projection_30m_flag=true
HINT matched without projection_period=30m
HINT matched without projection_30m_type=volume_up/shrink_down
HINT matched with non-empty triggered_periods/all_trigger_periods
HINT matched with primary_trigger_period not null
projection_30m_volume_up_flag and projection_30m_shrink_down_flag both true
projection_30m_type inconsistent with volume/shrink flags
payload contains final action_mark
```

## N5/N6 Follow-Up Requirements

N5 must later add an input guard under `layer_role=N5_action`:

```text
consume only TriggerMatched as action-confirmation input
verify signal_type is B_BUY/S_SELL
verify condition_signal_type is one of the six approved values
accept HINT trigger_period=30m only with empty formal period fields
reject ordinary/FULL trigger_period=30m
reject any 30m in formal period sets
ignore TriggerPendingMarketData and TriggerStateChanged for action creation
do not infer final action_mark from trigger_mark_candidate
```

N6 must later add display mapping under `layer_role=N6_user`:

```text
display condition_signal_type separately from signal_type
show 30m projection markers from projection fields
show requested/triggered formal periods from formal period fields
never treat N4 HINT/FULL names as voice/mobile/sim/trade intent
```

These are follow-up requirements only. This gate does not authorize N5/N6 implementation or execute.

## Forbidden Scope Proof

```text
n4_execute=false
db_write=false
outbox_inbox_checkpoint_consumed_or_updated=false
n5_entered=false
n6_entered=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_order_trade_real_trade=false
old_system_touched=false
```

## Validation

```text
source proposal JSON parse=PASS
HINT implementation report JSON parse=PASS
FULL implementation report JSON parse=PASS
contract/spec consistency review=PASS
```

## Next Gate

Allowed next gate:

```text
N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT_GATE
```

If that gate confirms payload-only with no physical migration, runtime_control may then hand off to:

```text
N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_DRY_RUN_ALIGNMENT_GATE
```
