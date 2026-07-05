# N4 Context Refresh Reader Alignment Dry-Run

Result: `DRY_RUN_PASS`

Layer role: `N4_trigger`

Stage: `N4_CONTEXT_REFRESH_READER_ALIGNMENT_DRY_RUN_GATE`

This gate did not execute N4 context refresh, did not write trigger state/match/outbox, did not consume/update outbox, did not enter N5/N6, and did not start a worker.

## Root Cause

`scripts/run_trigger_context_snapshot_execute.py` calls `ashare_v3.trigger.context_preflight.build_trigger_context_preflight_dry_run()`.

Before this fix, the N4 context reader built candidates only from:

- `stock/index/board_minute_target_scope`
- `stock/index/board_condition_pool`
- `stock/index/board_condition_basis`

It selected `period_trigger_baseline_json` with this legacy fallback:

```text
COALESCE(scope.period_trigger_baseline_json, pool.period_trigger_baseline_json, basis.period_trigger_baseline_json)
```

That path missed the N2 semantic refresh materialization rows in:

- `stock_condition_context_enrichment`
- `index_condition_context_enrichment`
- `board_condition_context_enrichment`

As a result, N4 saw legacy `previous_*` fields or missing `trigger_previous_*` fields.

## Reader Alignment

The reader now uses Option B.

It reads N2 materialized enrichment tables directly from DB and filters by:

- `materialization_run_id`
- `source_condition_run_id`
- `for_trade_date`
- `source_minute_target_scope_id`
- `identity_key`
- `condition_key`
- `direction`

The target materialization run is:

```text
trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1
```

N4 still does not read raw K, does not read N1 daily, does not self-aggregate, and does not read a dry-run payload artifact as the primary source.

## Dry-Run Summary

```text
candidate rows = 5118
stock/index/board = 4186/20/912
P0/P1/P2 = 0/0/0
period_trigger_baseline_json_missing = 0
trigger_previous_entity_high/low missing = 0
trigger_previous_amount_baseline missing = 0
baseline_source_trade_date mismatch = 0
legacy previous used as trigger baseline = 0
required_period_not_ready_rows = 0
```

## Sample Proof

`stock:SZ:002399`, `BUY:Y,Q,M,W,D`, D:

```text
trigger_previous_entity_high = 9.66
trigger_previous_entity_low = 9.45
trigger_previous_amount_baseline = 43678.117
baseline_source_trade_date = 20260604
legacy previous_entity_high trace = 9.79
legacy previous_entity_low trace = 9.67
```

`index:SZ:399006`, `BUY:W,D`, D:

```text
trigger_previous_entity_high = 4088.88
trigger_previous_entity_low = 4072.55
trigger_previous_amount_baseline = 703241125888
baseline_source_trade_date = 20260604
legacy previous_entity_high trace = 4122.99
legacy previous_entity_low trace = 4089.02
```

## Boundary Proof

```text
target execute common_trigger_run/state/match/outbox/inbox/checkpoint = 0/0/0/0/0/0
context downstream trigger_state/match/outbox = 0/0/0
N5 action_run/action_event refs = 0/0
N6 user_projection/signal/card/notification refs = 0/0/0/0
```

No DB writes were performed.

## Next Gate

Allowed:

```text
N4_CONTEXT_REFRESH_EXECUTE_CONTRACT_GATE
```

Still forbidden:

```text
N4 TriggerMatched execute
N5/N6
outbox consumption
worker
delivery / push / voice / mobile / sim / position / real trade
```
