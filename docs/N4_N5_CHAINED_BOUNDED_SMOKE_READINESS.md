# N4->N5 Chained Bounded Smoke Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T17:59:38+08:00`

Layer role: `runtime_control`

This gate is read-only readiness planning. It did not start a worker, did not execute N4 or N5, did not write the database, did not consume or update N3/N4/N5 outbox/inbox/checkpoint, and did not enter N6.

## Prerequisite Proof

```text
N5 rollback readiness=READINESS_PASS
N5 rollout registration=REGISTRATION_PASS
N5 scoped consumption smoke=POST_REVIEW_PASS
N5 semantic action smoke=POST_REVIEW_PASS
N4 rollout registration refresh=REGISTRATION_PASS
N4 day-scope bounded consumption smoke=POST_REVIEW_PASS
N4 worker rollout policy contract=CONTRACT_PASS
long_running_worker_approval=false
```

The existing N4 and N5 bounded smoke rows are registered evidence. They are not blockers for the proposed chained run because the proposed run uses a new action run id and consumer name.

## N4 Source Readiness Proof

Target source:

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type=TriggerMatched
```

Read-only live proof:

```text
transaction_read_only=on
TriggerMatched pending=556
delivered/delivering=0/0
required envelope/payload fields present=556/556
distinct event_id/dedup_key=556/556
selected candidate events=50
selected candidate asset distribution stock/index/board=50/0/0
selected candidate metric join coverage=50/50
N4 outbox locked/updated/consumed=false
```

Metric binding proof:

```text
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
metric_run.status=passed
metric_run.P0/P1/P2=0/1/0
metric rows stock/index/board=412/60/84
selected deterministic metric join coverage=50/50
opaque N4 payload action_confirmation trusted=false
```

The inherited metric P1 is not a readiness blocker for this gate. The chained contract gate must preserve the metric binding and re-prove selected event coverage before any execute authorization.

## N5 Target Baseline Proof

Proposed target:

```text
action_run_id=n4_n5_chained_bounded_smoke_20260608_unified_output_retry_probe
consumer_name=n5_action_worker_v1_n4_n5_chained_bounded_smoke_probe
```

Read-only baseline:

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
common_position_state/common_position_event=0/0
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
N6 virtual refs=0
delivery_attempt_refs=0
status_json_exists=false
stop_file_exists=false
```

Existing N5 smoke boundary:

```text
scoped consumption smoke N5 outbox rows=0
semantic action smoke N5 outbox pending=50
semantic action smoke N5 outbox delivered/delivering=0/0
```

Existing smoke rows must remain scoped to their own lineages and must not be modified by this readiness gate.

## Proposed Chained Bounded Smoke Scope

```text
mode=semantic_action_bounded_smoke
action_run_id=n4_n5_chained_bounded_smoke_20260608_unified_output_retry_probe
consumer_name=n5_action_worker_v1_n4_n5_chained_bounded_smoke_probe
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
source_event_type=TriggerMatched
metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
max_events=50
max_runtime_seconds=120
heartbeat_interval_seconds=10
status_json=docs/N4_N5_CHAINED_BOUNDED_SMOKE_STATUS.json
stop_file=tmp/n4_n5_chained_bounded_smoke_20260608_unified_output_retry_probe.stop
```

Expected writes only if a future contract, preflight, final gate, and user confirmation authorize execute:

```text
common_action_run=1
common_action_quality_item=as planned by contract
stock/index/board_action_fact<=50 total
common_action_event<=50
N5 common_event_outbox<=50
common_event_inbox<=50
common_event_consumer_checkpoint<=50
common_position_state=0
common_position_event=0
N4 outbox status update=0
N5 outbox consumption/update=0
N6/user/delivery/sim/trade refs=0
```

## Safety Requirements

```text
must_remain_bounded=true
requires_contract_preflight_final_gate=true
requires_rollback_sql_before_execute=true
requires_user_confirmation_before_execute=true
max_events_required=true
max_runtime_seconds_required=true
heartbeat_interval_seconds_required=true
status_json_required=true
stop_file_required=true
long_running_worker_allowed=false
N3_outbox_update_allowed=false
N4_outbox_status_update_allowed=false
N5_outbox_consumption_allowed=false
N6_entry_allowed=false
delivery_push_voice_mobile_allowed=false
sim_position_pnl_real_trade_allowed=false
proposal_order_trade_allowed=false
old_system_touch_allowed=false
```

The future chained smoke must be an N5 scoped bounded run over existing N4 `TriggerMatched` outbox events. It must not start or execute N4, must not acknowledge N4 outbox rows, and must not consume N5 outbox rows.

## Rollback Planning

Future rollback SQL path:

```text
sql/N4_N5_chained_bounded_smoke_20260608_unified_output_retry_probe_rollback.sql
```

Required rollback properties:

```text
scoped_by_action_run_id=true
scoped_by_consumer_name=true
hard_fail_before_first_DELETE_UPDATE=true
guard_N4_source_outbox_delivered_delivering=true
guard_N5_outbox_delivered_delivering=true
guard_N6_user_delivery_sim_order_trade_position_refs=true
delete_only_scoped_chained_smoke_rows=true
preserve_N4_N3_N2_N1_facts=true
preserve_existing_N5_lineages=true
no_CASCADE_DROP_TRUNCATE=true
rollback_executable_now=false
```

If downstream refs appear later, rollback must proceed in reverse order from downstream N6/user/sim/order/trade/position rows before deleting N5 action/outbox/inbox/checkpoint rows.

## Forbidden Scope Proof

```text
read_only_scope_query_executed=true
write_SQL_executed=false
database_written=false
N4_N5_execute=false
N3_N4_N5_outbox_inbox_checkpoint_consumed_or_updated=false
N6_entered=false
worker_started=false
long_running_worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
rollback_SQL_executed=false
```

## P Counts

```text
P0=0
P1=1
P2=0
P1_detail=inherited_metric_run_p1_warning_non_blocking
```

## Validation

```text
JSON parse=PASS
referenced prerequisite artifacts parse=PASS
live N4 source readiness proof=PASS
metric binding proof=PASS
target N5 baseline proof=PASS
existing smoke boundary proof=PASS
downstream refs baseline proof=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

## Decision

`READINESS_PASS`

Allowed next gate:

```text
N4_N5_CHAINED_BOUNDED_SMOKE_CONTRACT_GATE
```

