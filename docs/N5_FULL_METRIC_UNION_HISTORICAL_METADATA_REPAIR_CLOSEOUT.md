# N5 Full Metric Union Historical Metadata Repair Closeout

Status: CLOSEOUT_PASS

Layer role: runtime_control

Generated at: 2026-06-06T22:21:33+08:00

## Scope

This closeout only registers the completed N5 full metric-union historical metadata repair. It did not execute SQL, did not write business data, did not run rollback, did not enter N6, did not consume or update outbox/inbox/checkpoint, and did not start any worker.

## Execute Summary

```text
execute_result=EXECUTED
post_review_result=POST_REVIEW_PASS
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1:5432
action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
repair_run_id=n5_full_metric_union_historical_metadata_repair_20260605_v1
common_action_event.payload_json updated=605
N5 common_event_outbox.payload_json updated=605
P0/P1/P2=0/0/0
```

Only historical payload metadata was repaired. The repair did not change action status, event identity, outbox status, N4 payload, N3 metric rows, or N6 projection/card rows.

## Blocked Reason Comparison

```text
metric_missing: 289 -> 0
price_confirmation_failed: 305 -> 587
amount_confirmation_failed: 10 -> 17
```

Live read-only proof after repair:

```text
ActionBlocked / blocked / failed / price_confirmation_failed = 587
ActionBlocked / blocked / failed / amount_confirmation_failed = 17
ActionExecuted / executed / passed = 1
metric_missing = 0
```

## Status Invariance

```text
ActionExecuted: 1 -> 1
ActionBlocked: 604 -> 604
ActionEligible: 0 -> 0
ActionSkipped: 0 -> 0
event_type changes=0
action_state changes=0
confirmation_status changes=0
action_mark changes=0
```

## Payload Scope

Allowed metadata keys:

```text
blocked_reason
action_confirmation_metric_run_refs
metric_union_policy_version
metric_union_source_runs
metric_coverage_status
metric_missing_resolved
repair_trace
```

Forbidden fields stayed unchanged:

```text
event_type
action_state
action_status
confirmation_status
action_mark
event_id
action_run_id
source_trigger_event_id
outbox status
delivery status
N4 payload
N3 metric rows
N6 projection/card
```

Live scoped metadata proof:

```text
common_action_event rows=605
N5 outbox rows=605
common_action_event policy refs=605
N5 outbox policy refs=605
common_action_event metric_missing after=0
N5 outbox metric_missing after=0
```

## Boundary Proof

```text
N4 TriggerMatched outbox pending=605
N5 ActionBlocked outbox pending=604
N5 ActionExecuted outbox pending=1
N5 outbox delivering/delivered=0/0
downstream inbox/checkpoint/delivery_attempt=0/0/0
N6 projection/card repair policy refs=0/0
user_notification_queue=0
position_state/position_event=0/0
virtual_order/virtual_trade/virtual_position=0/0/0
worker_started=false
real_trade=false
```

Existing N6 projection/card rows from the earlier projection run were not updated in this gate; this closeout only confirms N5 metadata repair completion.

## Rollback Summary

Rollback SQL:

```text
sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql
```

Rollback static proof:

```text
RAISE EXCEPTION before first UPDATE=true
executable DELETE/INSERT/CASCADE/DROP/TRUNCATE=0
scope only restores common_action_event/common_event_outbox payload metadata
does not touch N4/N3/N2/N1/N6 facts
guards delivered/delivering, inbox/checkpoint, delivery attempts, N6 propagation, notification, position, virtual refs
```

## Validation

```text
JSON parse: passed
execute/post-review artifact existence: passed
rollback static check: passed
git diff --check: passed
```

## Next Gate

Recommended:

```text
N6_FULL_METRIC_UNION_HISTORICAL_PROJECTION_REPAIR_CONTRACT_GATE
```

Alternative if historical N6 display repair is intentionally deferred:

```text
DEFER_N6_PROJECTION_REPAIR_AND_CLOSE_BRANCH_GATE
```
