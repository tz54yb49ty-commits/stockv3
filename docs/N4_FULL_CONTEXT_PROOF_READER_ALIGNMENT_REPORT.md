# N4 FULL Context Proof Reader Alignment Report

Result: **ALIGNMENT_PASS**

Layer role: `N4_trigger`

Generated at: `2026-06-09T17:34:22+08:00`

This gate only repaired N4 reader/alignment code, tests, and this report. It did
not execute N4 matcher, write business database rows, consume or update
outbox/inbox/checkpoint, start a worker, enter N5/N6, execute rollback, or
touch old-system / delivery / push / voice / mobile / sim / position / order /
trade / real-trade surfaces.

## Root Cause Diagnosis

The previous FULL semantic repair removed the old global
`full_condition_matched_forbidden` rule and correctly introduced a strict FULL
D-period whitelist. However, the projection matcher passed raw context rows to
`evaluate_v4_plan`.

For 20260608 until 15:00, the persisted N4 context rows have:

- `condition_key=BUY:FULL / SELL:FULL`
- `condition_periods=["D"]`
- `allowed_signal_types` as N4 expanded runtime candidates, such as
  `B_BUY,B_BUY_30M_VOL` or `S_SELL,S_SELL_30M_SHRINK`
- source condition pool / basis / minute target scope IDs
- `period_trigger_baseline_json`

But the row did not expose `original_condition_key` as a top-level field after
`projection_matcher.normalize_context_row`. The v4 FULL guard then saw
`original_condition_key=""` and blocked every FULL row as
`full_n2_context_missing` before D transition / amount-chain evaluation.

So the blocker was not FULL policy. It was reader/alignment proof loss.

## Code Repair Summary

Modified:

- `src/ashare_v3/trigger/projection_matcher.py`
  - `normalize_context_row` now preserves `condition_key` /
    `original_condition_key` from `raw_json` when present.
  - If `original_condition_key` is absent but `condition_key` is present, it
    sets `original_condition_key=condition_key`. For N4 localized context, the
    top-level `condition_key=BUY:FULL/SELL:FULL` is the N2 FULL proof.
  - `build_projection_matcher_plans` now normalizes every context row before
    routing it to hint/formal evaluation.

- `tests/test_trigger_projection_matcher.py`
  - Added coverage for FULL proof preservation.
  - Added BUY:FULL / SELL:FULL projection matcher tests proving the rows reach
    D whitelist evaluation and can become `TriggerMatched`.
  - Added regression proving mismatched `original_condition_key` still blocks
    with `full_n2_context_missing`.

No change was made to N5/N6 or to database facts.

## FULL Context Proof Fields Preserved

Read-only DB proof after the repair:

```text
run_status=passed
full_count=86
full_distribution:
  stock BUY:FULL=47
  stock SELL:FULL=35
  board SELL:FULL=4
original_missing=0
original_mismatch=0
condition_periods_not_d=0
baseline_missing=0
source_condition_pool_missing=0
source_condition_basis_missing=0
source_scope_missing=0
```

Sample normalized FULL row:

```json
{
  "trigger_context_id": 47157,
  "condition_key": "BUY:FULL",
  "original_condition_key": "BUY:FULL",
  "direction": "buy",
  "condition_periods": ["D"],
  "allowed_signal_types": ["B_BUY", "B_BUY_30M_VOL"],
  "source_condition_run_id": "condition_layer_20260605_to_20260608_v13_index_all_execute",
  "source_condition_pool_id": 138218,
  "source_condition_basis_id": 154544,
  "source_minute_target_scope_id": 125105
}
```

## Regression Proof

Tests added or updated prove:

- `normalize_context_row` preserves FULL proof fields.
- BUY:FULL context with proof reaches `evaluate_v4_plan` and no longer produces
  `full_n2_context_missing`.
- SELL:FULL context with proof reaches `evaluate_v4_plan` and no longer
  produces `full_n2_context_missing`.
- Missing or mismatched N2 FULL proof still blocks.
- Ordinary BUY/SELL paths do not self-derive FULL.
- HINT 30m semantics remain unchanged.

Validation:

```text
PYTHONPATH=src python3 -m unittest \
  tests/test_trigger_projection_matcher.py \
  tests/test_n4_trigger_rule_v4_matcher.py \
  tests/test_n4_v4_enforcement.py

Ran 51 tests in 0.005s
OK

PYTHONPATH=src python3 scripts/check_n4_contract.py
passed=true
finding_count=0

python3 -m compileall src/ashare_v3/trigger tests
PASS
```

## Forbidden Scope Proof

Live read-only DB proof for the new FULL repair retry run remains clean:

```text
common_trigger_match=0
common_trigger_state=0
common_event_outbox=0
common_event_inbox=0
common_event_consumer_checkpoint=0
N5 refs=0
N6 refs=0
```

Boundary flags:

```text
N4 matcher execute=false
business DB write=false
outbox/inbox/checkpoint consume_or_update=false
rollback_executed=false
N5_entered=false
N6_entered=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```

## Decision

`ALIGNMENT_PASS`

Allowed next gate:

```text
N4_PROJECTION_MATCHER_20260608_UNTIL_1500_FULL_REPAIR_RETRY_REGENERATION_GATE
```
