# N5 Worker Larger Scope Semantic Smoke Post Review

Result: `POST_REVIEW_PASS`

Generated at: `2026-06-10T19:36:38+08:00`

Layer role: `runtime_control`

This post-review is read-only. It did not execute SQL, did not write database rows, did not consume or update N4/N5 outbox/inbox/checkpoint, did not enter N6, did not start a worker, and did not execute rollback SQL.

## Target

```text
action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
consumer_name=n5_action_worker_v1_larger_scope_semantic_action_smoke_probe
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type=TriggerMatched
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
max_events=200
```

## Execute Proof Summary

```text
execute_report_json_parse=PASS
status_json_parse=PASS
execute_report.result=EXECUTED
normalized_result=EXECUTE_PASS
common_action_run.status=passed
P0/P1/P2=0/0/0
allow_execute=true
blockers=[]
worker_started=false
long_running_worker_started=false
N4_outbox_status_updated=false
N4_outbox_consumed=false
N6_user_layer_touched=false
```

## Row Count Proof

Actual writes match final gate planned:

```text
common_action_run=1
common_action_quality_item=0
stock_action_fact=56
index_action_fact=60
board_action_fact=84
common_action_event=200
N5 common_event_outbox=200
common_event_inbox=200
common_event_consumer_checkpoint=194
common_position_state=0
common_position_event=0
```

## Semantic Distribution Proof

```text
ActionBlocked=199
ActionExecuted=1
ActionEligible=0
ActionSkipped=0
action_state blocked/executed=199/1
confirmation_status failed/passed=199/1
blocked_reason price_confirmation_failed=194
blocked_reason amount_confirmation_failed=5
action_mark null=199
N5 outbox pending=200
N5 outbox delivered/delivering=0/0
legacy ActionEvent/HintEvent/RiskEvent/PositionEvent=0
```

The single `ActionExecuted` row is an N5 market action confirmation fact/event only. It does not imply real order, sim, N6 display, delivery, or trade intent.

## Metric Binding Proof

```text
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
deterministic metric join coverage=200/200
duplicate_join_key_count=0
missing_n4_rows=0
common_action_event metric trace=200/200
stock_action_fact metric trace=56/56
index_action_fact metric trace=60/60
board_action_fact metric trace=84/84
opaque payload.action_confirmation trusted=false
```

Metric trace distribution:

```text
board=84
index=60
stock=56
```

## N4 Source Preservation Proof

```text
N4 TriggerMatched pending=556
N4 delivered/delivering=0/0
selected N4 source events via N5 inbox still pending=200
N4 outbox status updated=false
N4 outbox consumed=false
N4 trigger facts unchanged_by_this_gate=true
```

## Downstream Forbidden Proof

```text
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
delivery_attempt refs=0
virtual_order/virtual_trade/virtual_position/virtual_pnl=0/0/0/0
common_position_state/common_position_event=0/0
N6/user refs=0
delivery/push/voice/mobile refs=0
sim/position/pnl/real_trade refs=0
proposal/order/trade refs=0
old_system_touched=false
```

## Rollback Proof

Rollback SQL:

```text
sql/N5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql
```

Static proof:

```text
rollback exists=true
rollback executed=false
disabled_by_default=true
hard-fail before first DELETE/UPDATE=true
guards N4 source outbox delivered/delivering=true
guards scoped N5 outbox delivered/delivering=true
guards N6/user/sim/order/trade/position refs=true
deletes only scoped larger semantic smoke rows if future rollback authorized=true
preserves N4/N3/N2/N1 facts and existing N5 lineages=true
no CASCADE/DROP/TRUNCATE=true
```

## Worker Readiness Implication

The N5 worker evidence now includes:

```text
scoped consumption-only smoke=POST_REVIEW_PASS
semantic action bounded smoke=POST_REVIEW_PASS
N4->N5 chained bounded semantic smoke=POST_REVIEW_PASS
larger-scope semantic action smoke=POST_REVIEW_PASS
deterministic metric binding at 200-event scope=PASS
ActionBlocked path evidence=199 rows
ActionExecuted path evidence=1 row
```

This is sufficient evidence for the next bounded rollout planning gates, including N6 projection bounded smoke readiness and N4->N5->N6 chained shadow smoke readiness.

This is not long-running N5 worker approval. It does not authorize N4 outbox ack/status changes, N5 outbox consumption by N6, N6 delivery, sim, or trade.

## Forbidden Scope Proof

```text
SQL_executed_by_this_gate=false
database_written_by_this_gate=false
N4_outbox_consumed_or_updated=false
N5_outbox_consumed_or_updated=false
N6_entered=false
worker_started=false
long_running_worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
rollback_executed=false
```

## Validation

```text
JSON parse=PASS
live row count proof=PASS
semantic distribution proof=PASS
metric binding proof=PASS
N4 source preservation proof=PASS
downstream refs scan=PASS
rollback static check=PASS
git diff --check=PASS
```

## Decision

`POST_REVIEW_PASS`.

The N5 worker larger-scope semantic action smoke can be marked complete.

Recommended next gate:

```text
N5_WORKER_ROLLOUT_REGISTRATION_REFRESH_GATE
```
