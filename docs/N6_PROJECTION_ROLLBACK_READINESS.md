# N6 Projection Rollback Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T20:33:00+08:00`

Layer role: `runtime_control`

This gate is read-only rollback planning. It did not execute rollback SQL, did not write database rows, did not consume or update N5 outbox, inbox, or checkpoint rows, did not start a worker, did not touch delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.

## Registration Prerequisite Proof

```text
N6 projection rollout registration=REGISTRATION_PASS
N6 bounded shadow projection post-review=POST_REVIEW_PASS
execute_report_result=EXECUTED
contract=CONTRACT_PASS
this_gate_authorizes_rollback_execution=false
```

## Live Scoped Row Proof

Live read-only DB proof:

```text
transaction_read_only=on
user_projection_run=1
user_signal_projection=200
user_signal_card=200
user_notification_queue=0
projection_distribution ActionBlocked/blocked=199
projection_distribution ActionExecuted/executed=1
matches_registered_post_review=true
```

## N5 Source Preservation Proof

Live read-only DB proof:

```text
ActionBlocked pending=199
ActionExecuted pending=1
pending_total=200
delivered/delivering total=0
N5 outbox status updated=false
N5 outbox consumed=false
N5 event inbox refs for source action run=0
N5 checkpoint refs for source action run=0
delivery attempt refs for source action run=0
```

## Downstream Refs Proof

Live read-only DB proof:

```text
user_signal_decision=0
user_sim_order=0
user_sim_trade=0
user_sim_position=0
common_position_state=0
common_position_event=0
n6_virtual_order=0
n6_virtual_trade=0
n6_virtual_position=0
n6_virtual_position_event=0
n6_virtual_pnl_snapshot=0
delivery/push/voice/mobile refs=0
sim/order/trade/position/PnL/virtual refs=0
proposal/order/trade refs=0
```

## Rollback SQL Proof

Rollback SQL:

```text
sql/N6_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe_rollback.sql
```

Static proof:

```text
exists=true
rollback_executed=false
disabled_by_default=true
hard_fail_before_first_DELETE_UPDATE=true
scoped_by_exact_user_projection_run_id=true
scoped_by_exact_source_action_run_id=true
guards_N5_outbox_delivered_delivering=true
guards_user_decision_sim_order_trade_position_PnL_virtual_refs=true
guards_delivery_push_voice_mobile_refs=true
delete_order=user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run
preserves_N5_action_facts_and_N5_outbox_status=true
preserves_N4_N3_N2_N1=true
no_CASCADE_DROP_TRUNCATE=true
```

## Readiness Decision

```text
rollback_readiness=READINESS_PASS
rollback_executable_now=false
rollback_requires_separate_final_gate=true
rollback_requires_explicit_user_confirmation=true
lineage_can_be_rolled_back_if_final_gate_authorized_and_guards_remain_clean=true
preserving_registered_smoke_evidence_is_currently_acceptable=true
if_downstream_refs_appear_then_reverse_order_rollback_required=true
existing_N6_projection_rows_should_not_be_silently_deleted=true
```

## Forbidden Scope Proof

```text
rollback_SQL_executed=false
SQL_executed=false
database_written=false
N5_outbox_inbox_checkpoint_consumed_or_updated=false
N6_execute_entered=false
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
referenced artifacts parse=PASS
live scoped row proof=PASS
N5 source preservation proof=PASS
downstream refs scan=PASS
rollback SQL static check=PASS
git diff --check=PASS
```

Recommended next gate:

```text
N4_N5_N6_CHAINED_SHADOW_SMOKE_READINESS_GATE
```
