# N5 Action Pipeline Metric Union Repair Dry-Run

Status: DRY_RUN_PASS

Layer role: N5_action

Generated at: 2026-06-06T08:23:00.405110+00:00

## Scope

```text
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
existing_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
repair_dry_run_id=action_consumer_action_pipeline_metric_union_repair_dry_run_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
old_metric_run_id=action_confirmation_projection_metric_20260605__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
latest_additive_metric_run_id=action_confirmation_projection_metric_20260605_repair_v1__trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

## Input Universe

```text
N4 TriggerMatched pending rows=605
N3 metric union rows=577
metric union join coverage=577/605
missing after union=28
duplicate join keys=0
```

## Planned Event Distribution

```text
{
  "ActionBlocked": 604,
  "ActionExecuted": 1
}
```

## Blocked Reason Distribution

```text
{
  "amount_confirmation_failed": 17,
  "metric_missing": 28,
  "price_confirmation_failed": 559
}
```

## Existing vs Planned Delta

```text
would_change_rows=261
no_change_rows=344
missing_existing_rows=0
event_type_transitions={"ActionBlocked->ActionBlocked": 261}
blocked_reason_transitions={"metric_missing->amount_confirmation_failed": 7, "metric_missing->price_confirmation_failed": 254}
```

## Feasibility

```text
feasible=True
future_db_write_required=True
rollback_required_for_future_execute=True
n6_projection_card_repair_separate_gate_required=true
```

## Boundary Proof

```text
writes_performed=false
N4 facts modified=false
N3 metric facts modified=false
N5/N4 outbox consumed=false
outbox status updated=false
inbox/checkpoint written=false
N6 touched=false
worker_started=false
voice/mobile/sim/position/pnl/real_trade=false
```

## Quality

```text
P0/P1/P2=0/0/0
```

## Validation

```text
JSON parse: passed
  python3 -m json.tool docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_DRY_RUN.json
  python3 -m json.tool docs/N5_ACTION_PIPELINE_METRIC_UNION_REPAIR_CONTRACT.json

compileall: passed
  python3 -m compileall scripts src tests

regression tests: passed
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action*.py'
  Ran 70 tests

planned rows assertion: passed
  coverage=577/605
  duplicate_join_key_count=0
  ActionBlocked=604
  ActionExecuted=1
  metric_missing=28
  P0=0
  writes_performed=false
  enter_n6=false

git diff --check: passed
```
