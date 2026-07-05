# N6 Projection Bounded Smoke Contract

Result: `CONTRACT_PASS`

Generated at: `2026-06-10T20:01:15+08:00`

## Target

```text
user_projection_run_id=user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_event_type=ActionBlocked / ActionExecuted
mode=shadow_projection_bounded_smoke
```

## Proof Summary

```text
readiness=READINESS_PASS
dry_run=DRY_RUN_PASS
N5 outbox ActionBlocked pending=199
N5 outbox ActionExecuted pending=1
N5 outbox delivered/delivering=0/0
target baseline user_projection_run/signal/card/queue=0/0/0/0
P0/P1/P2=0/5/2
```

## Planned Write Scope

```text
user_projection_run=1
user_signal_projection=200
user_signal_card=200
user_notification_queue=0
user_signal_decision=0
user_session=0
user_watchlist=0
user_watchlist_item=0
user_sim_order=0
user_sim_trade=0
user_sim_position=0
common_position_state=0
common_position_event=0
n5_outbox_status_updates=0
n5_outbox_consumption=0
delivery_push_voice_mobile=0
proposal_order_trade=0
real_trade=0
```

## Notification Queue Policy

```text
dry_run_candidate_user_notification_queue=200
notification_queue_policy=deferred
future_execute_user_notification_queue=0
delivery/push/voice/mobile=false
```

## Rollback

```text
rollback_sql=sql/N6_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe_rollback.sql
rollback_executed=false
hard_fail_before_first_DELETE_UPDATE=true
guards_n5_outbox_delivered_delivering=true
guards_delivery_sim_trade_position_refs=true
no_CASCADE_DROP_TRUNCATE=true
```

## Forbidden Scope

```text
n6_execute_by_this_gate=false
database_written_by_this_gate=false
n5_outbox_consumed_or_updated=false
n5_inbox_checkpoint_consumed_or_updated=false
worker_started=false
long_running_worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl_real_trade=false
proposal_order_trade=false
old_system_touched=false
rollback_executed=false
```

Allowed next gate: `N6_PROJECTION_BOUNDED_SMOKE_EXECUTE_USER_CONFIRMATION_GATE`
