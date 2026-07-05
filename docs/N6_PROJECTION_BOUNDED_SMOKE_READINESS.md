# N6 Projection Bounded Smoke Readiness

Result: `READINESS_PASS`

Generated at: `2026-06-10T19:50:47+08:00`

Layer role: `runtime_control`

This readiness gate is read-only. It did not execute N6, did not write database rows, did not consume or update N5 outbox, inbox, or checkpoint rows, did not start a worker, did not touch delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade.

## Prerequisite Proof

```text
N5_WORKER_ROLLOUT_REGISTRATION_REFRESH=REGISTRATION_PASS
N5 larger-scope semantic action smoke=POST_REVIEW_PASS
N4->N5 chained bounded semantic smoke=POST_REVIEW_PASS
N5 semantic action bounded smoke=POST_REVIEW_PASS
N5 scoped consumption-only smoke=POST_REVIEW_PASS
N5 rollback readiness=READINESS_PASS for original scoped consumption + semantic action lineages
N4 worker rollout registration refresh=REGISTRATION_PASS
```

Readiness decision inherited from N5 rollout registration refresh:

```text
N5 bounded worker foundation evidence sufficient for N6 projection bounded smoke readiness=true
long-running N5 worker approval=false
N4 outbox ack/status update approval=false
N5 outbox consumption by N6 approval=false
N6 projection execute approval=false
N6 delivery/sim/trade approval=false
```

## N5 Source Readiness Proof

Target source:

```text
source_action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_event_type=ActionBlocked / ActionExecuted
source_layer=N5_action
```

Live read-only DB proof:

```text
transaction_read_only=on
N5 outbox ActionBlocked pending=199
N5 outbox ActionExecuted pending=1
N5 outbox delivered/delivering=0/0
pending canonical input total=200
distinct event_id=200
distinct dedup_key=200
N5 outbox consumed_by_this_gate=false
N5 outbox status_updated_by_this_gate=false
```

Larger-scope semantic action smoke source proof:

```text
stock/index/board_action_fact=56/60/84
common_action_event=200
N5 common_event_outbox=200
common_event_inbox=200
common_event_consumer_checkpoint=194
ActionBlocked/ActionExecuted/ActionEligible/ActionSkipped=199/1/0/0
blocked_reason price_confirmation_failed=194
blocked_reason amount_confirmation_failed=5
metric_binding=200/200
N4 source preservation=true
downstream refs=0
```

The single `ActionExecuted` source event is display/projection input only for this future N6 smoke. It is not order, trade, delivery, push, voice, mobile, sim, position, PnL, real trade, or proposal approval.

## N6 Target Baseline Proof

Proposed projection run:

```text
user_projection_run_id=user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
```

Live read-only scoped baseline:

```text
user_projection_run=0
user_signal_projection=0
user_signal_card=0
user_notification_queue=0
```

Live read-only downstream refs:

```text
user_signal_decision=0
user_sim_order=0
user_sim_trade=0
user_sim_position=0
common_position_state=0
common_position_event=0
common_event_delivery_attempt=0
```

Existing N5 smoke rows remain registered evidence and are not modified by this gate.

## Proposed N6 Projection Bounded Smoke Scope

Future contract should target:

```text
gate=N6_PROJECTION_BOUNDED_SMOKE_CONTRACT_GATE
user_projection_run_id=user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_event_type=ActionBlocked / ActionExecuted
expected_n5_outbox_counts=ActionBlocked:pending=199, ActionExecuted:pending=1
mode=shadow projection bounded smoke
```

Expected writes if a later contract/final gate is authorized:

```text
user_projection_run=1
user_signal_projection=200
user_signal_card=200
user_notification_queue=0
user_signal_decision=0
user_session=0
user_watchlist/user_watchlist_item=0/0
user_sim_order/user_sim_trade/user_sim_position=0/0/0
common_position_state/common_position_event=0/0
N5 outbox status update=0
N5 outbox consumption=0
delivery/push/voice/mobile=0
sim/position/pnl/real_trade=0
proposal/order/trade=0
```

Projection/card rows must preserve:

```text
source_action_run_id
source_event_id
source_event_type
source_event_dedup_key
action_state=blocked/executed
blocked_reason for ActionBlocked
action_mark only for ActionExecuted
metric_run_id / metric trace when present
N4/N5 lineage trace
```

## Safety Requirements

```text
must remain run-once / bounded by source_action_run_id and explicit expected N5 outbox counts
must not long-run
must not consume/update N5 outbox status
must not write N5 inbox/checkpoint
must not read N4/N5 naked facts as substitute for N5 standard events
must not enter delivery/push/voice/mobile
must not touch sim/position/pnl/real_trade
must not create proposal/order/trade
must not touch old system
contract/preflight/final gate required before any execute
rollback SQL required before any execute
```

Existing N6 projection runner support is sufficient for the next contract gate:

```text
plan_n6_projection_dry_run supports canonical ActionBlocked / ActionExecuted inputs
run_n6_projection_once requires --execute and --user-confirmed before DB writes
run_n6_projection_once writes only N6 projection/card/optional queue rows
run_n6_projection_once does not consume or update N5 outbox
```

## Rollback Planning

Rollback SQL must be generated before any execute and scoped to:

```text
user_projection_run_id=user_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe__n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
source_action_run_id=n5_worker_larger_scope_semantic_action_smoke_20260608_unified_output_retry_probe
rollback_sql=sql/N6_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe_rollback.sql
```

Rollback must:

```text
hard-fail before first DELETE/UPDATE
guard N5 outbox delivered/delivering
guard notification/delivery/push/voice/mobile refs
guard user decision/sim/order/trade/position/PnL refs
delete only scoped N6 bounded smoke rows
delete in reverse order: user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run
preserve N5 action facts and N5 outbox status
preserve N4/N3/N2/N1 facts and existing N5 smoke lineages
contain no CASCADE/DROP/TRUNCATE
```

Rollback is not authorized by this readiness gate.

## Forbidden Scope Proof

```text
N6_executed=false
SQL_write_executed=false
database_written=false
N5_outbox_consumed_or_updated=false
N5_inbox_checkpoint_consumed_or_updated=false
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
referenced artifacts parse=PASS
live N5 source readiness proof=PASS
live N6 target baseline proof=PASS
downstream refs scan=PASS
runner static support proof=PASS
rollback requirement proof=PASS
forbidden scope proof=PASS
git diff --check=PASS
```

## P0/P1/P2

```text
P0=0
P1=0
P2=0
```

## Decision

`READINESS_PASS`

Allowed next gate:

```text
N6_PROJECTION_BOUNDED_SMOKE_CONTRACT_GATE
```
