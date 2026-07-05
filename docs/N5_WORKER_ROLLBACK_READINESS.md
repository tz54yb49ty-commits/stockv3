# N5 Worker Rollback Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T17:51:37+08:00`

Layer role: `runtime_control`

This gate is read-only rollback planning. It used read-only live proof and static rollback SQL checks. It did not execute rollback SQL, did not write the database, did not consume or update N4/N5 outbox/inbox/checkpoint, did not enter N6, and did not start a worker.

## Registration Prerequisite Proof

```text
rollout_registration=REGISTRATION_PASS
scoped_consumption_post_review=POST_REVIEW_PASS
semantic_action_post_review=POST_REVIEW_PASS
rollback_execution_authorized=false
```

Target N5 smoke lineages:

```text
scoped_consumption:
  run_id=n5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe
  consumer=n5_action_worker_v1_scoped_consumption_smoke_probe

semantic_action:
  run_id=n5_worker_semantic_action_smoke_20260608_unified_output_retry_probe
  consumer=n5_action_worker_v1_semantic_action_smoke_probe
```

## Live Scoped Row Proof

Read-only transaction proof:

```text
transaction_read_only=on
N4 TriggerMatched source pending=556
N4 delivered/delivering=0/0
```

Scoped consumption lineage:

```text
common_action_run=1
common_action_run.status=passed
P0/P1/P2=0/0/0
worker_started=false
common_action_quality_item=6
stock/index/board_action_fact=0/0/0
common_action_event=0
N5 common_event_outbox=0
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state/common_position_event=0/0
selected N4 source events pending=50
```

Semantic action lineage:

```text
common_action_run=1
common_action_run.status=passed
P0/P1/P2=0/0/0
worker_started=false
common_action_quality_item=0
stock/index/board_action_fact=0/0/50
common_action_event=50
N5 common_event_outbox=50
N5 outbox pending/delivered/delivering=50/0/0
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state/common_position_event=0/0
selected N4 source events pending=50
ActionBlocked=50
blocked_reason price_confirmation_failed=50
```

## Downstream Refs Proof

Both lineages have downstream refs total `0`.

Scoped consumption:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
user_signal_decision_via_projection=0
user_sim_order/trade/position=0/0/0
common_position_state/event=0/0
n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0
common_event_delivery_attempt_for_n5_outbox=0
```

Semantic action:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
user_signal_decision_via_projection=0
user_sim_order/trade/position=0/0/0
common_position_state/event=0/0
n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0
common_event_delivery_attempt_for_n5_outbox=0
```

## Rollback SQL Proof

Scoped consumption rollback:

```text
path=sql/N5_worker_scoped_consumption_smoke_20260608_unified_output_retry_probe_rollback.sql
exists=true
hard_fail_before_first_DELETE_UPDATE=true
scoped_run_id_present=true
scoped_consumer_name_present=true
guards_N4_source_outbox_delivered_delivering=true
guards_N5_outbox_delivered_delivering=true
guards_N6_user_sim_order_trade_position_refs=true
preserves_N4_N3_N2_N1_by_scope=true
no_CASCADE_DROP_TRUNCATE=true
rollback_not_executed=true
```

Semantic action rollback:

```text
path=sql/N5_worker_semantic_action_smoke_20260608_unified_output_retry_probe_rollback.sql
exists=true
hard_fail_before_first_DELETE_UPDATE=true
scoped_run_id_present=true
scoped_consumer_name_present=true
guards_N4_source_outbox_delivered_delivering=true
guards_N5_outbox_delivered_delivering=true
guards_N6_user_sim_order_trade_position_refs=true
preserves_N4_N3_N2_N1_by_scope=true
no_CASCADE_DROP_TRUNCATE=true
rollback_not_executed=true
```

## Readiness Decision

```text
READINESS_PASS=true
rollback_executable_now=false
requires_separate_rollback_final_gate=true
requires_user_confirmation_before_rollback=true
existing_N5_smoke_rows_are_registered_evidence=true
preserve_smoke_evidence_preferred=true
```

Both lineages are rollback-ready only under a future rollback final gate. The semantic action lineage has N5 outbox rows, so any future rollback must keep the N5 outbox delivered/delivering guard at zero and must re-scan downstream refs immediately before execution.

If downstream refs appear later, rollback must proceed in reverse order from downstream N6/user/sim/order/trade/position rows before deleting N5 action/outbox/inbox/checkpoint rows. N4/N3/N2/N1 facts and existing non-smoke N5 lineages must be preserved.

## Forbidden Scope Proof

```text
read_only_scope_query_executed=true
write_SQL_executed=false
rollback_SQL_executed=false
database_written=false
N4_N5_outbox_inbox_checkpoint_consumed_or_updated=false
N6_entered=false
worker_started=false
long_running_worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
```

## Validation

```text
JSON parse=PASS
registration prerequisite proof=PASS
live scoped row proof=PASS
downstream refs scan=PASS
rollback SQL static check=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

## Decision

`READINESS_PASS`

Rollback readiness is registered. Rollback is not authorized by this gate. The next recommended rollout gate is:

```text
N4_N5_CHAINED_BOUNDED_SMOKE_READINESS_GATE
```

If the user explicitly wants to remove existing N5 smoke evidence rows, open a separate rollback final gate first.
