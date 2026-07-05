# N1-N5 Remaining Layer Repair Blockers Registration

Gate: `N1_N5_REMAINING_LAYER_REPAIR_BLOCKERS_REGISTRATION_GATE`

Result: `BLOCKED_BY_LAYER_BOUNDARY_REGISTERED`

Layer role: `runtime_control`

This registration covers the four findings that remain after the runtime-control repairs:

- `N1N5-P0-001`
- `N1N5-P1-001`
- `N1N5-P1-002`
- `N1N5-P2-002`

Runtime-control already closed:

- `N1N5-P0-002`
- `N1N5-P1-003`
- `N1N5-P2-001`

## Fresh Readonly Proof

Fresh DB proof time: `2026-06-08T22:06:47.612336+08:00`

Source trigger run:

```text
trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

Action run:

```text
action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

N4 proof:

- `common_trigger_match` rows: `605`
- N4 `TriggerMatched` outbox rows: `605`
- outbox payload required v4 fields present: `605/605`
- `common_trigger_match.raw_json` required v4 keys present:
  - `trigger_kind`: `0`
  - `triggered_periods`: `0`
  - `all_trigger_periods`: `0`
  - `primary_trigger_period`: `0`
  - `trigger_live`: `0`
  - `current_status`: `0`
  - `n5_entry_allowed`: `0`
  - `match_basis`: `0`

N5 proof:

- `common_action_run` rows: `1`
- `common_action_run.status`: `passed`
- `common_action_run P0/P1/P2`: `0/0/0`
- `common_action_event` rows: `605`
- N5 outbox pending:
  - `ActionBlocked=604`
  - `ActionExecuted=1`
- inbox rows for source trigger run: `605`
- inbox status: `processed=605`
- checkpoint rows scoped to this action run: `73`
- checkpoint key: `consumer_name + partition_key + source_layer`

## Remaining Findings

### N1N5-P0-001

Owner: `N5_action`

Root cause:

The execute report embeds stale N5-5 dry-run diagnostic quality under `dry_run_plan.quality`. That nested dry-run compares against `docs/N5_ACTION_PIPELINE_EXECUTE_CONTRACT.json` as if it were an N5-1 baseline and derives `baseline_read_event_count=0`, so it reports a P0 failed item even though the execute gate top-level quality and persisted `common_action_run` are `P0/P1/P2=0/0/0`.

Required gate:

```text
N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE
```

### N1N5-P1-001

Owner: `N4_trigger`

Root cause:

N4 corrected execute persists v4-required fields in `TriggerMatched` outbox payload, while `common_trigger_match` facts keep a narrower legacy shape. The current artifacts do not explicitly say whether `common_trigger_match` may be payload-only for these fields.

Required gate:

```text
N4_V4_TRIGGER_MATCH_FACT_SCHEMA_OR_PAYLOAD_ONLY_POLICY_GATE
```

### N1N5-P1-002

Owner: `N5_action`

Root cause:

N5 artifacts use `checkpoint_write_plan_count=605` as if it were physical `common_event_consumer_checkpoint` rows. Live DB shows `605` processed inbox events but only `73` checkpoint rows scoped to this `action_run_id`, because checkpoint is a per-partition watermark keyed by `consumer_name + partition_key + source_layer` and only rows whose watermark advances are updated.

Implementation note:

`src/ashare_v3/action/execute.py` currently returns `len(rows)` from `upsert_checkpoints`, not the number of physical rows inserted/updated after the `ON CONFLICT ... WHERE last_outbox_id advances` clause.

Required gate:

```text
N5_CHECKPOINT_ROWCOUNT_ALIGNMENT_GATE
```

### N1N5-P2-002

Owner: `N4_trigger`

Root cause:

Legacy `projection_matcher_execute` remains present with inbox/outbox/checkpoint write paths. Current corrected N4 runners avoid it, but no strong route-selection/deprecation guard prevents future gate confusion.

Required gate:

```text
N4_LEGACY_ROUTE_DEPRECATION_AND_SELECTION_GUARD_GATE
```

## Forbidden Scope Proof

- N4/N5 code modified: false
- database writes: false
- business execute: false
- rollback executed: false
- outbox consumed or updated: false
- worker started: false
- N6 implementation entered: false
- proposal/order/trade/position/PnL/real trade touched: false

## Next Required Prompt

```text
layer_role=N5_action。

进入 N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE。
```
