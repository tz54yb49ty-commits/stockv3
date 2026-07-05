# N6 Projection Rollout Registration

Result: `REGISTRATION_PASS`

Generated at: `2026-06-10T20:24:00+08:00`

Layer role: `runtime_control`

This gate is documentation-only. It did not execute SQL, did not write database rows, did not consume or update N5 outbox, inbox, or checkpoint rows, did not start a worker, did not enter delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade, and did not execute rollback SQL.

## N6 Projection Evidence Summary

```text
N6 projection bounded shadow smoke post-review=POST_REVIEW_PASS
execute result=EXECUTED / EXECUTE_PASS
preflight_result=PREFLIGHT_PASS
notification_queue_policy=deferred
P0/P1/P2=0/5/2
allowed write tables=user_projection_run,user_signal_projection,user_signal_card
user_projection_run=1
user_signal_projection=200
user_signal_card=200
user_notification_queue=0
ActionBlocked=199
ActionExecuted=1
can_mark_N6_bounded_shadow_projection_smoke_complete=true
```

The P1/P2 items are non-blocking shadow projection enrichment warnings. They do not authorize N4/N5 naked fact backfill, delivery, sim, trade, or worker execution.

## N5 Source Preservation Proof

```text
source_action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_event_type=ActionBlocked / ActionExecuted
pending_total=200
ActionBlocked pending=199
ActionExecuted pending=1
delivered/delivering=0/0
N5 outbox status updated=false
N5 outbox consumed=false
N5 inbox/checkpoint refs for source action run=0/0
delivery_attempt_refs=0
```

## Scope Evidence

```text
N4 worker rollout registration refresh=REGISTRATION_PASS
N5 worker rollout registration refresh=REGISTRATION_PASS
N5 larger-scope semantic action smoke=POST_REVIEW_PASS
N4->N5 chained bounded semantic smoke=POST_REVIEW_PASS
N6 projection rows scoped to user_projection_run_id=true
N5 source rows remain registered evidence=true
N5 outbox from larger-scope smoke remains pending=true
N5 outbox consumption/update authorized=false
delivery/push/voice/mobile refs=0
decision/sim/order/trade/position/PnL/virtual refs=0
proposal/order/trade refs=0
worker_started=false
long_running_worker_started=false
old_system_touched=false
```

## Readiness Decision

```text
N6 projection bounded foundation evidence registered=true
N6 projection evidence sufficient for next shadow chained planning=true
N6 bounded shadow projection smoke complete=true
long-running worker approval=false
N5 outbox consumption/update policy change authorized=false
delivery/push/voice/mobile authorized=false
sim/position/PnL/real_trade authorized=false
proposal/order/trade authorized=false
existing N4/N5/N6 smoke rows are registered evidence=true
future rollback must be scoped and reverse-order aware=true
```

This registration supports moving to the next planning gate. It does not authorize N5 outbox consumption, N5 outbox status changes, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, trade, or long-running worker execution.

## Remaining Blockers / Required Next Gates

P0:

```text
none
```

P1:

```text
N6 projection rollback readiness for newly created bounded smoke rows before any rollback execution
N5 outbox ack/consume policy remains unapproved
N6 delivery/push/voice/mobile policy remains unapproved
N6 sim/position/PnL/real_trade policy remains unapproved
N4->N5->N6 chained shadow smoke readiness not yet registered
long-running worker lifecycle/heartbeat/stop/drain policy remains unapproved
```

Recommended sequence:

```text
A. N6_PROJECTION_ROLLBACK_READINESS_GATE
B. N4_N5_N6_CHAINED_SHADOW_SMOKE_READINESS_GATE
C. N6_DELIVERY_NOOP_OR_NOTIFICATION_POLICY_READINESS_GATE
D. N6_SIM_POSITION_SHADOW_READINESS_GATE only after explicit policy gate
E. LONG_RUNNING_WORKER_READINESS_GATE only after all bounded gates pass
```

## Rollback Strategy

```text
existing N6 projection smoke rows should not be silently deleted=true
rollback_sql=sql/N6_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe_rollback.sql
rollback execution authorized by this gate=false
rollback must be scoped by user_projection_run_id=true
rollback user_projection_run_id=user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
rollback must guard N5 outbox delivered/delivering=true
rollback must guard delivery/push/voice/mobile refs=true
rollback must guard user decision/sim/order/trade/position/PnL/virtual refs=true
rollback delete order=user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run
if downstream refs exist rollback must proceed reverse order=true
preserve N5/N4/N3/N2/N1 facts and existing N4/N5 lineages=true
no CASCADE/DROP/TRUNCATE=true
```

## Forbidden Scope Proof

```text
SQL_executed=false
database_written=false
rollback_SQL_executed=false
N5_outbox_inbox_checkpoint_consumed_or_updated=false
N6_execute_entered_by_this_gate=false
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
forbidden scope proof=PASS
git diff --check=PASS
```

Recommended next gate:

```text
N6_PROJECTION_ROLLBACK_READINESS_GATE
```
