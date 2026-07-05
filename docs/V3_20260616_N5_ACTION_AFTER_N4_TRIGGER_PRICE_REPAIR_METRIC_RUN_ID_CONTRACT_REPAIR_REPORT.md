# V3 20260616 N5 Action Metric Run ID Contract Repair Report

- result: `REPAIR_PASS`
- layer_role: `N5_action`
- mode: `artifact_repair_only`
- database_written: `false`
- n5_execute_performed: `false`

## Root Cause

The previous execute attempt was blocked by `n5_execute_consumer_guard` with `dedicated_consumer_metric_run_id_missing`.
The dedicated replay consumer contract had `source_metric_run_id`, but the runner guard requires top-level `metric_run_id`.

## Repair

Added top-level `metric_run_id` to:

- `docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_CONTRACT.json`
- `docs/V3_20260616_N5_ACTION_AFTER_N4_TRIGGER_PRICE_REPAIR_PREFLIGHT.json`

Value:

```text
action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1
```

Markdown artifacts were updated to show the metric run and N4 outbox payload trigger price source proof.

## Unchanged Scope

- source N4 run: `v3_n4_trigger_replay_20260616_until_1401_v1`
- action_run_id: `v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1`
- consumer: `n5_action_consumer_v1_20260616_trigger_price_repair_replay`
- rollback SQL: `sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql`

## Planned Distribution Unchanged

```text
ActionExecuted=18
ActionBlocked=522
ActionEligible=0
ActionSkipped=0
common_action_event=540
common_event_outbox=540
stock/index/board_action_fact=478/18/44
```

## Live Baseline

```text
N4 outbox:
  TriggerMatched pending=540
  TriggerPendingMarketData pending=4158
  delivered/delivering=0/0

target N5 scoped rows=0
N6/user/position refs=0
```

## Rollback

Rollback SQL unchanged. Static check confirms:

```text
hard-fail before first DELETE/UPDATE=true
guards delivered/delivering=true
guards downstream inbox/checkpoint=true
guards N6/user refs=true
does not delete N4/N3 facts=true
```

## Validation

```text
contract/preflight JSON parse=PASS
metric_run_id top-level assertion=PASS
dedicated consumer guard artifact assertion=PASS
planned distribution unchanged assertion=PASS
live DB read-only baseline proof=PASS
rollback static check=PASS
git diff --check=PASS
```

Runtime control may retry the execute final gate review.
