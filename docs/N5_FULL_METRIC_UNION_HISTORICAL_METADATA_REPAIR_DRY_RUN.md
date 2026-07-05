# N5 Full Metric Union Historical Metadata Repair Dry-Run

Status: CONTRACT_PASS

Layer role: N5_action

Generated at: 2026-06-06T13:28:43.744205+00:00

## Scope

```text
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
source_trigger_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
repair_run_id=n5_full_metric_union_historical_metadata_repair_20260605_v1
execute_authorized=false
```

## Full Metric Union

```text
original metric rows=316
additive_v1 rows=261
board metric_v2 rows=28
coverage=605/605
duplicate metric join key=0
missing metric after union=0
```

## Old/New Comparison

```text
scoped N5 action rows=605
unchanged_action_status=605
changed_blocked_reason rows=289
metric_missing before/after=289/0
price_confirmation_failed before/after=305/587
amount_confirmation_failed before/after=10/17
ActionExecuted before/after=1/1
ActionBlocked before/after=604/604
ActionSkipped before/after=0/0
ActionEligible before/after=0/0
```

## Payload Repair Plan

```text
planned_payload_update_rows=605
target=common_action_event.payload_json, N5 common_event_outbox.payload_json
allowed_metadata_keys=blocked_reason, action_confirmation_metric_run_refs, metric_union_policy_version, metric_union_source_runs, metric_coverage_status, metric_missing_resolved, repair_trace
forbidden=event_type/action_state/confirmation_status/action_mark/event_id/source ids/outbox status/N4 payload/N6 projection card
```

## Quality

```text
P0/P1/P2=0/0/0
```

## Forbidden Scope Proof

```text
writes_performed=false
outbox_consumed=false
outbox_status_updated=false
inbox_checkpoint_updated=false
N4/N3/N2 modified=false
N6 projection/card modified=false
worker_started=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
```

## Validation

```text
JSON parse: passed
payload parse: passed, rows=605, allowed_metadata_keys_only=true
rollback static check: passed
  hard_fail_before_update=true
  no DELETE/INSERT/CASCADE/DROP/TRUNCATE=true
  updates_only=common_action_event, common_event_outbox
  no N4/N3/N2/N6 mutation=true
compileall: passed
  python3 -m compileall scripts src tests
targeted tests: passed
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action*.py' (70 tests)
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n3_action_confirmation_metric_materialization_execute.py' (22 tests)
boundary scan: passed
  N4 common_trigger_match/outbox=605/605
  N5 outbox pending ActionBlocked/ActionExecuted=604/1
  N5 downstream inbox/checkpoint/delivery=0/0/0
  existing N6 projection/card refs are present but not touched
git diff --check: passed
```
