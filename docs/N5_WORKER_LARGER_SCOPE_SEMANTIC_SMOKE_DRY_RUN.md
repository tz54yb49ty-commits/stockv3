# N5 Worker Larger Scope Semantic Smoke Dry Run

Result: `DRY_RUN_PASS`

Generated at: `2026-06-10T19:22:10+08:00`

Layer role: `runtime_control`

This dry-run only generated and reviewed a deterministic plan. It did not execute N5, did not write the database, did not consume or update N4/N5 outbox, did not enter N6, and did not start a worker.

## Target

```text
action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
consumer_name=n5_action_worker_v1_larger_scope_semantic_action_smoke_probe
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type=TriggerMatched
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
semantic_action_smoke=true
max_events=200
max_runtime_seconds=300
heartbeat_interval_seconds=10
```

## Source Readiness

```text
N4 TriggerMatched total=556
pending=556
delivered/delivering=0/0
selected_events=200
selected_all_pending=true
selected_by_asset_kind board/index/stock=84/60/56
distinct_event_id/dedup_key=200/200
N4 outbox status update=0
N4 outbox consumption=0
```

## Metric Binding

```text
metric_run.status=passed
metric rows stock/index/board=412/60/84
deterministic join coverage=200/200
duplicate_join_key_count=0
missing_n4_rows=0
opaque payload.action_confirmation trusted=false
```

## Semantic Dry-Run Summary

```text
ActionBlocked=199
ActionExecuted=1
ActionEligible=0
ActionSkipped=0
planned_action_fact_count=200
planned_output_event_count=200
common_event_inbox=200
common_event_consumer_checkpoint=194
```

Planned fact split:

```text
stock_action_fact=56
index_action_fact=60
board_action_fact=84
```

Planned signal split:

```text
B_BUY=62
S_SELL=138
buy=62
sell=138
BUY_HINT rows=11
SELL_HINT rows=3
deprecated runtime signal rows=0
```

## Planned Write Scope If Future Execute Is Authorized

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

## Forbidden Scope Proof

```text
database_written=false
N4_outbox_consumed_or_updated=false
N5_outbox_consumed_or_updated=false
N6_entered=false
worker_started=false
long_running_worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```
