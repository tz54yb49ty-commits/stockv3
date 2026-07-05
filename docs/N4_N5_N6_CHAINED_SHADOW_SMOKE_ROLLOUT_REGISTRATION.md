# N4->N5->N6 Chained Shadow Smoke Rollout Registration

Result: `REGISTRATION_PASS`

Generated at: `2026-06-10T21:04:17+08:00`

Layer role: `runtime_control`

This gate is documentation-only. It did not execute SQL, did not write database rows, did not consume or update N4/N5 outbox, inbox, or checkpoint rows, did not start a worker, did not touch delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade, and did not execute rollback SQL.

## Chained Shadow Evidence Summary

```text
amended_post_review=POST_REVIEW_PASS
can_mark_N4_N5_N6_chained_shadow_smoke_complete=true
original_postcheck_result=BLOCKED
original_blocker=n6_notification_queue_planned_actual_mismatch
alignment=ALIGNMENT_PASS
N4 leg=read-only source preservation; no new N4 writes
N5 execute result=EXECUTED
N5 common_action_run.status=passed
N5 P0/P1/P2=0/0/0
N6 execute result=EXECUTED
N6 preflight_result=PREFLIGHT_PASS
N6 P0/P1/P2=0/5/2
worker_started=false
long_running_worker_started=false
```

N5 staged smoke rows:

```text
common_action_run=1
common_action_quality_item=0
stock/index/board_action_fact=0/0/50
common_action_event=50
N5 common_event_outbox=50
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state/common_position_event=0/0
ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped=50/0/0/0
```

N6 amended shadow projection rows:

```text
user_projection_run=1
user_signal_projection=50
user_signal_card=50
user_notification_queue=50
user_signal_decision=0
projection_distribution ActionBlocked/ActionExecuted=50/0
```

## Queued-Only Notification Amendment Summary

The original final gate planned `user_notification_queue=0`, but the runner wrote `user_notification_queue=50`. The policy alignment gate registered the root cause as a contract artifact field mismatch: the chained contract planned deferred notification semantics but did not expose top-level `notification_queue_policy=deferred`, so the N6 runner used its immediate default.

The amended policy decision is:

```text
ACCEPT_QUEUED_ONLY_SHADOW_ROWS_BY_ALIGNMENT_AMENDMENT
rollback_required_now=false
rerun_required_now=false
matches_original_final_gate=false
matches_amended_queue_policy=true
```

Queue safety:

| queue_status | channel | notification_source | count |
|---|---|---|---:|
| `queued_only` | `broadcast_queue` | `n5_action_blocked` | 50 |

Additional proof:

```text
not_queued_only=0
non_broadcast_queue=0
actual_push=false
voice_mobile_push=false
provider_delivery_attempt=false
```

Future deferred N6 projection executes must include top-level `notification_queue_policy=deferred` in the contract/preflight JSON.

## N4/N5 Source Preservation Proof

N4 source outbox:

```text
source_trigger_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
TriggerMatched pending=556
delivered/delivering=0/0
N4 outbox status updated=false
N4 outbox consumed=false
```

Scoped N5 outbox:

```text
source_action_run_id=n4_n5_n6_chained_shadow_smoke_20260608_action_probe
pending=50
delivered/delivering=0/0
N5 outbox status updated by N6=false
N5 outbox consumed by N6=false
N5 inbox/checkpoint refs for N6 source=0/0
```

## Scope Evidence

```text
N4 worker rollout registration refresh=REGISTRATION_PASS
N5 worker rollout registration refresh=REGISTRATION_PASS
N6 projection rollout registration=REGISTRATION_PASS
all chained rows scoped to dedicated run ids=true
N5 action_run_id=n4_n5_n6_chained_shadow_smoke_20260608_action_probe
N5 consumer=n5_action_worker_v1_n4_n5_n6_chained_shadow_probe
N6 user_projection_run_id=n4_n5_n6_chained_shadow_smoke_20260608_projection_probe
N4 outbox status updated=false
N5 outbox status updated=false
N5 outbox consumed by N6=false
delivery/push/voice/mobile refs=0
user_signal_decision=0
sim/position/PnL/real_trade refs=0
proposal/order/trade refs=0
old_system_touched=false
```

## Readiness Decision

```text
N4_N5_N6_chained_shadow_smoke_registered=true
chained_shadow_evidence_sufficient_for_next_rollout_planning=true
chained_shadow_evidence_sufficient_for_rollback_readiness_refresh=true
can_enter_delivery_noop_or_notification_policy_readiness=true
can_enter_long_running_worker_readiness=false
long_running_worker_approval=false
N4_outbox_ack_status_update_authorized=false
N5_outbox_consumption_update_authorized=false
delivery_push_voice_mobile_authorized=false
sim_position_pnl_real_trade_authorized=false
proposal_order_trade_authorized=false
queued_only_rows_are_registered_shadow_evidence=true
existing_smoke_rows_must_not_be_silently_deleted=true
future_rollback_must_be_scoped_and_reverse_order_aware=true
```

This registration supports the next bounded planning and rollback-readiness gates. It does not authorize long-running workers, N4/N5 outbox ack or status mutation, N5 outbox consumption, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.

## Remaining Blockers / Required Next Gates

P0:

```text
none
```

P1:

```text
N4/N5/N6 chained shadow smoke rollback readiness has not yet been refreshed after the amended post-review
future deferred N6 projection contracts must expose top-level notification_queue_policy=deferred
N4 outbox ack/status update policy remains unapproved
N5 outbox consumption/update policy remains unapproved
delivery/push/voice/mobile policy remains unapproved
sim/position/PnL/real_trade policy remains unapproved
long-running worker lifecycle/heartbeat/stop/drain policy remains unapproved
```

P2:

```text
N6 shadow projection enrichment warnings remain non-blocking
original blocked postcheck remains preserved as historical evidence and must be read with the alignment amendment
```

Recommended sequence:

```text
A. N4_N5_N6_CHAINED_SHADOW_SMOKE_ROLLBACK_READINESS_GATE
B. N6_DELIVERY_NOOP_OR_NOTIFICATION_POLICY_READINESS_GATE
C. N6_SIM_POSITION_SHADOW_READINESS_GATE only after explicit policy gate
D. LONG_RUNNING_WORKER_READINESS_GATE only after all bounded rollback/policy gates pass
```

## Rollback Strategy

Rollback is not authorized by this registration.

```text
rollback_sql=sql/N4_N5_N6_chained_shadow_smoke_20260608_probe_rollback.sql
rollback_executed=false
rollback_must_be_scoped_by_run_ids_and_consumer=true
rollback_n6_user_projection_run_id=n4_n5_n6_chained_shadow_smoke_20260608_projection_probe
rollback_n5_action_run_id=n4_n5_n6_chained_shadow_smoke_20260608_action_probe
rollback_n5_consumer_name=n5_action_worker_v1_n4_n5_n6_chained_shadow_probe
rollback_must_guard_N4_source_outbox_delivered_delivering=true
rollback_must_guard_N5_scoped_outbox_delivered_delivering=true
rollback_must_guard_user_delivery_sim_order_trade_position_refs=true
rollback_delete_order=user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run -> N5 inbox/checkpoint/outbox/action facts/run
preserve_N4_N5_source_outbox_status=true
preserve_N4_N3_N2_N1_facts=true
preserve_existing_N4_N5_N6_lineages=true
no_CASCADE_DROP_TRUNCATE=true
separate_rollback_final_gate_required=true
```

## Forbidden Scope Proof

```text
SQL_executed=false
database_written=false
rollback_SQL_executed=false
N4_N5_N6_execute_entered=false
N4_outbox_consumed_or_updated=false
N5_outbox_consumed_or_updated=false
N4_N5_outbox_inbox_checkpoint_consumed_or_updated=false
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
evidence consistency=PASS
queued-only amendment consistency=PASS
rollback static evidence referenced=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

Recommended next gate:

```text
N4_N5_N6_CHAINED_SHADOW_SMOKE_ROLLBACK_READINESS_GATE
```
