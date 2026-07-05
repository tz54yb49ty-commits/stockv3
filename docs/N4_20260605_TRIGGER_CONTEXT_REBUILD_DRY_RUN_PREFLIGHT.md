# N4 20260605 Trigger Context Rebuild Dry-Run / Preflight Gate

Result: `DRY_RUN_PREFLIGHT_PASS`

Layer role: `N4_trigger`

This gate is read-only for business data. It did not execute context rebuild, did not write trigger context/state/match/outbox, did not consume outbox, did not start workers, and did not enter N5/N6.

## Lineage

- source_condition_run_id: `condition_layer_20260604_source_20260604_v1`
- market_subscription_run_id: `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source_market_data_run_id: `realtime_snapshot_20260605_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- target_context_run_id: `trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1`
- target_execute_run_id: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`

## Expected Context Rows

| Asset | Rows |
|---|---:|
| stock | 4186 |
| index | 20 |
| board | 912 |
| total | 5118 |

Object coverage by asset: `{'stock': 1952, 'index': 9, 'board': 428}`

BUY_HINT / SELL_HINT trace rows: `212/130`

`period_trigger_baseline_json_missing=0`

`required_period_not_ready_rows=0`

## Field Readiness

Core fields ready: `True`

Context rebuild localizes N2 scope/pool/basis rows plus `period_trigger_baseline_json`. N4 v4 matcher-only fields such as `trigger_kind`, `n5_entry_allowed`, `triggered_periods`, `all_trigger_periods`, `primary_trigger_period`, `triggered_period_details`, and `outcome_classification` are produced by the v4 matcher dry-run, not by `trigger_context_snapshot`.

Market subscription trace:

- traced_context_row_count: `5118`
- untraced_context_row_count: `0`
- subscription_row_count: `3073`
- subscription_object_count: `2389`

Read-scope proof:

```text
reads_n2_scope_pool_basis=true
reads_n3_subscription_trace=true
reads_raw_k=false
reads_n1_daily=false
self_aggregation=false
pulls_market_data=false
consumes_outbox=false
```

## Scoped Baseline

```json
{
  "common_trigger_run": 0,
  "common_trigger_quality_item": 0,
  "stock_trigger_context_snapshot": 0,
  "index_trigger_context_snapshot": 0,
  "board_trigger_context_snapshot": 0,
  "common_trigger_state": 0,
  "common_trigger_match": 0,
  "common_event_outbox": 0,
  "common_event_inbox": 0,
  "common_event_consumer_checkpoint": 0,
  "target_execute_common_trigger_run": 0,
  "target_execute_common_trigger_state": 0,
  "target_execute_common_trigger_match": 0,
  "target_execute_common_event_outbox": 0
}
```

Downstream refs:

```json
{
  "common_action_run": 0,
  "common_action_event": 0,
  "user_projection_run": 0,
  "user_signal_projection": 0,
  "user_signal_card": 0,
  "user_notification_queue": 0
}
```

## Quality

P0/P1/P2=`0/0/0`

Failed checks, if any, are listed in the JSON artifact.

## Rollback Proof

Rollback SQL: `sql/N4_20260605_trigger_context_rebuild_rollback.sql`

Proof:

- `RAISE EXCEPTION` appears before first `DELETE FROM`.
- Guards cover N4 outbox/inbox/checkpoint, trigger_state, trigger_match, N5 action_run/action_event, and optional N6 user projection / signal / card / notification refs.
- DELETE scope is limited to `common_trigger_quality_item`, stock/index/board trigger context snapshot tables, and `common_trigger_run` for the target context run.
- Rollback does not touch N2/N3 facts, N4 trigger execute rows, N5/N6, or outbox/inbox/checkpoint rows.

## Future Execute Scope

Allowed only after user final confirmation:

```text
common_trigger_run
common_trigger_quality_item
stock_trigger_context_snapshot
index_trigger_context_snapshot
board_trigger_context_snapshot
```

Forbidden:

```text
common_trigger_state
common_trigger_match
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N5/N6
worker
delivery / push / voice / mobile / sim / position / real trade
```

## Decision

Context rebuild final gate allowed: `True`

Local trigger dry-run remains blocked until context rebuild execute passes.
