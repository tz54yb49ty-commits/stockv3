# N4 Unified Trigger Signal Output Schema Impact

Result: **SCHEMA_IMPACT_PASS**

Layer role: `N4_trigger`

Generated at: `2026-06-09`

This gate reviewed schema impact and code-alignment scope only. It did not execute N4, did not write database rows, did not execute schema migration, did not consume or update outbox/inbox/checkpoint, did not enter N5/N6, and did not start workers.

## Inputs

- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_REVIEW.md`
- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_REVIEW.json`
- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.md`
- `docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_CONTRACT_PROPOSAL.json`
- `docs/N4_TRIGGER_RULE_SPEC_v4.md`
- `docs/N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`
- `docs/N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.json`
- `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.md`
- `docs/N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_REPORT.json`
- `docs/V3_TRIGGER_ACTION_RUNTIME_SPEC.md`
- `src/ashare_v3/trigger/*`
- `src/ashare_v3/events/models.py`
- `tests/test_n4*.py`
- `tests/test_trigger_projection_matcher*.py`

## Decision

```text
payload_only_approved=true
physical_schema_migration_required_now=false
schema_migration_execute_authorized=false
```

The unified trigger signal output can land first in payload / raw_json / report artifacts without adding physical columns in this gate.

Approved payload-only targets:

```text
common_event_outbox.payload_json
common_trigger_state.raw_json
common_trigger_match.raw_json
N4 dry-run JSON / markdown reports
N4 preflight JSON / markdown reports
N4 execute contract JSON / markdown reports
N4 execute report JSON / markdown reports
```

## Schema Feasibility Proof

`common_event_outbox` already stores canonical event data in `payload_json`.

`common_trigger_state` already has `raw_json JSONB` and currently writes a nested plan object in N4 execute paths.

`common_trigger_match` already has `raw_json JSONB` and currently mirrors v4 required fields at the top level in at least the standard execute path.

Existing physical columns already cover the high-frequency lookup fields needed by current write paths:

```text
run_id
source_condition_run_id
for_trade_date
asset_kind
identity_key
direction
signal_type
condition_key
trigger_period
trigger_bucket
trigger_live
trigger_mark_candidate
primary_trigger_period
all_trigger_periods
projection_30m_flag
projection_30m_type
current_status
data_quality_status
trigger_price
trigger_time
output_event_type
raw_json
```

The newly approved unified fields are not required as physical columns to satisfy current uniqueness constraints, row lookup constraints, rollback scope, or downstream event protocol. They can be persisted as payload/raw_json proof first.

## Required Unified Fields

The canonical unified payload field set for the next dry-run/code alignment gate is:

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

The earlier proposal JSON omitted `triggered_period_details` from `required_unified_fields`. This schema impact gate does not rewrite that historical proposal artifact. Instead, it carries forward runtime_control's review correction:

```text
triggered_period_details is required in future contract/dry-run alignment artifacts.
```

## Payload-Only Storage Contract

For future N4 writes, payload-only means:

1. `common_event_outbox.payload_json` is the canonical cross-layer proof for N5/N6.
2. `common_trigger_match.raw_json` must mirror the unified fields for persisted `TriggerMatched` rows so cross-layer audit does not need to infer from nested payloads only.
3. `common_trigger_state.raw_json` must include the unified field envelope for state rows, including `TriggerPendingMarketData` state rows where no `common_trigger_match` row is written.
4. Reports must expose summary counts and samples for the unified fields and P0 guards.

This policy preserves existing physical schema while making future N4 output self-describing.

## No Immediate Physical Migration

No physical columns are required now.

No table is altered in this gate.

Potential future additive columns may be reviewed later if query/display performance requires them:

```text
common_trigger_state.condition_signal_type
common_trigger_state.requested_periods
common_trigger_state.projection_30m_required
common_trigger_state.projection_30m_volume_up_flag
common_trigger_state.projection_30m_shrink_down_flag

common_trigger_match.condition_signal_type
common_trigger_match.requested_periods
common_trigger_match.triggered_period_details
common_trigger_match.projection_30m_required
common_trigger_match.projection_30m_volume_up_flag
common_trigger_match.projection_30m_shrink_down_flag
```

These columns are not approved for migration here. If needed, they require a separate schema migration draft / final gate / user confirmation.

## Required Code And Report Alignment Scope

The next N4 dry-run/code alignment gate may modify only N4-owned artifacts:

```text
N4 payload builder / event factory / normalizer
N4 v4 enforcement guard
N4 dry-run reports
N4 preflight reports
N4 execute contract reports
N4 execute report schema
N4 tests
N4 docs/artifacts
```

Expected code alignment:

```text
derive condition_signal_type from condition_key/original_condition_key/N2 provenance
emit runtime_signal_type equal to signal_type
emit requested_periods parsed from formal condition keys
emit triggered_period_details for formal matched rows
emit empty triggered_period_details for HINT matched rows
emit projection_30m_required on every output
emit projection_30m_volume_up_flag / projection_30m_shrink_down_flag on every output
mirror unified payload in common_trigger_match.raw_json for TriggerMatched
mirror unified payload in common_trigger_state.raw_json for state/pending rows
keep action_mark absent from N4 payload
```

Disallowed in the next N4 alignment gate:

```text
N5 implementation
N6 implementation
schema migration execution
business execute
outbox consumption
worker startup
```

## P0 Guard Carry-forward

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
HINT matched missing triggered_period_details field
HINT matched with non-empty triggered_period_details
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

## HINT And Formal Period Policy

HINT `TriggerMatched`:

```text
condition_signal_type=BUY_HINT / SELL_HINT
trigger_kind=hint
trigger_period=30m
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
triggered_period_details=[]
projection_period=30m
projection_30m_required=true
projection_30m_flag=true
projection_30m_type=volume_up / shrink_down
```

Formal ordinary / FULL `TriggerMatched`:

```text
condition_signal_type=BUY / SELL / BUY:FULL / SELL:FULL
trigger_kind=trigger
trigger_period in Y/Q/M/W/D
triggered_periods non-empty
all_trigger_periods non-empty
primary_trigger_period in Y/Q/M/W/D
triggered_period_details non-empty
projection_30m_required=false unless future policy explicitly approves otherwise
```

## Impacted Tables

No physical schema change now.

Payload/raw_json validation affects future writes to:

```text
common_event_outbox
common_trigger_state
common_trigger_match
```

No migration affects:

```text
N1 facts
N2 facts
N3 facts
common_event_inbox
common_event_consumer_checkpoint
N5 action tables
N6 user/sim tables
```

## Validation Performed

```text
read-only file review=true
schema migration executed=false
database write=false
business execute=false
json artifact generated=true
```

Static validation commands for this gate:

```text
python3 -m json.tool docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT.json
git diff --check -- docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT.md docs/N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_SCHEMA_IMPACT.json
```

## Forbidden Scope Proof

```text
n4_execute=false
database_write=false
schema_migration_execute=false
outbox_inbox_checkpoint_consumed_or_updated=false
n5_entered=false
n6_entered=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_order_trade_real_trade=false
old_system_touched=false
```

## Next Gate

Allowed next gate:

```text
N4_UNIFIED_TRIGGER_SIGNAL_OUTPUT_DRY_RUN_ALIGNMENT_GATE
```

The next gate must implement payload-only unified fields, add/refresh tests, and regenerate dry-run/preflight artifacts. It must still not execute N4 business unless a later final gate and explicit user confirmation approve it.
