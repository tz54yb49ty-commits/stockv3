# N5 Worker Larger Scope Semantic Smoke Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T18:35:51+08:00`

Layer role: `runtime_control`

This gate is readiness-only. It did not execute N5, did not write database rows, did not consume or update N4/N5 outbox/inbox/checkpoint, did not enter N6, and did not start a worker.

## Target Proposed Smoke

- Action run id: `n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe`
- Consumer: `n5_action_worker_v1_larger_scope_semantic_action_smoke_probe`
- Source trigger run: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- Source event type: `TriggerMatched`
- Metric run id: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- Semantic action smoke: `true`
- Max events: `200`
- Max runtime seconds: `300`
- Heartbeat interval seconds: `10`
- Status JSON: `docs/N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_STATUS.json`
- Stop file: `tmp/n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe.stop`

## Prerequisite Proof

```text
N4_N5_CHAINED_BOUNDED_SMOKE_POST_REVIEW=POST_REVIEW_PASS
N5_WORKER_SEMANTIC_ACTION_SMOKE_POST_REVIEW=POST_REVIEW_PASS
N5_WORKER_SCOPED_CONSUMPTION_SMOKE_POST_REVIEW=POST_REVIEW_PASS
N5_WORKER_ROLLBACK_READINESS=READINESS_PASS
N5_WORKER_ROLLOUT_REGISTRATION=REGISTRATION_PASS
N4_WORKER_BOUNDED_SMOKE_ROLLOUT_REGISTRATION_REFRESH=REGISTRATION_PASS
N4_PROJECTION_MATCHER_POST_REVIEW=POST_REVIEW_PASS
N3_ACTION_CONFIRMATION_METRIC_POST_REVIEW=POST_REVIEW_PASS
```

Runner proof:

```text
semantic_action_smoke_runner_alignment=ALIGNMENT_PASS
runner supports --semantic-action-smoke=true
runner supports --metric-run-id
runner supports bounded max_events/max_runtime/heartbeat/status_json/stop_file
runner keeps N4 outbox status update disabled
runner keeps N6/delivery/sim/trade paths disabled
```

## Source Readiness Proof

Live read-only proof used a read-only PostgreSQL session:

```text
transaction_read_only=on
N4 TriggerMatched total=556
pending=556
delivered/delivering=0/0
pending_by_asset board/index/stock=84/60/412
selected_events=200
selected_all_pending=true
selected_all_TriggerMatched=true
selected_by_asset board/index/stock=84/60/56
distinct_event_id=200
distinct_dedup_key=200
event_id/dedup_key/partition_key/event_schema_version/payload_json present=200/200
N4 outbox locked=false
N4 outbox status updated=false
N4 outbox consumed=false
```

## Metric Binding Readiness Proof

```text
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
metric_run.status=passed
metric rows stock/index/board=412/60/84
metric rows total=556
deterministic metric join coverage=200/200
duplicate_join_key_count=0
missing_n4_rows=0
direct_metric_fact_rows=200
opaque payload.action_confirmation trusted=false
```

Selected metric join distribution:

```text
board joined=84/84
index joined=60/60
stock joined=56/56
```

## Target Baseline Proof

Target scoped rows are all zero:

```text
common_action_run=0
common_action_quality_item=0
stock_action_fact=0
index_action_fact=0
board_action_fact=0
common_action_event=0
N5 common_event_outbox=0
common_event_inbox=0
common_event_consumer_checkpoint=0
common_position_state=0
common_position_event=0
status_json_exists=false
stop_file_exists=false
```

Downstream target refs are also zero:

```text
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
common_event_delivery_attempt=0
virtual_order/trade/position/pnl=0
```

## Proposed Larger Semantic Smoke Scope

Future execute, if separately authorized by contract/preflight/final gate, should remain scoped to:

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

Planned write scope from read-only deterministic dry-plan:

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

Semantic distribution expected for the selected 200:

```text
ActionBlocked=199
ActionExecuted=1
ActionEligible=0
ActionSkipped=0
N5 entry from TriggerMatched only=true
```

## Safety Requirements

- The next gate must regenerate dry-run / contract / preflight / final gate review.
- The next execute, if authorized, must remain bounded by `max_events`, `max_runtime_seconds`, `heartbeat_interval_seconds`, `status_json`, and `stop_file`.
- No N4 outbox status update is allowed.
- No N5 outbox consumption/update is allowed.
- No N6/user delivery projection is allowed.
- No delivery/push/voice/mobile is allowed.
- No sim/position/PnL/real_trade is allowed.
- No proposal/order/trade is allowed.
- Existing N4/N5 smoke lineages must remain untouched.

## Rollback Planning

Required rollback draft for the next contract gate:

```text
sql/N5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql
```

The rollback draft must:

```text
scope by exact action_run_id and consumer_name
hard-fail before first DELETE/UPDATE
guard N4 source outbox delivered/delivering
guard scoped N5 outbox delivered/delivering
guard N6/user/sim/order/trade/position refs
delete only scoped larger semantic smoke rows if rollback is separately authorized
preserve N4/N3/N2/N1 facts and existing N5 lineages
avoid CASCADE/DROP/TRUNCATE
remain unexecuted in contract/readiness gates
```

## Forbidden Scope Proof

```text
N5_executed=false
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

## P0/P1/P2

```text
P0=0
P1=0
P2=0
```

## Decision

`READINESS_PASS`.

The prerequisites, source readiness, deterministic metric binding, target baseline, downstream boundary, and rollback planning are sufficient to enter:

```text
N5_WORKER_LARGER_SCOPE_SEMANTIC_SMOKE_CONTRACT_GATE
```

This readiness does not authorize execute, long-running workers, N4 outbox ack/status changes, N5 outbox consumption, N6, delivery, sim, or trade.
