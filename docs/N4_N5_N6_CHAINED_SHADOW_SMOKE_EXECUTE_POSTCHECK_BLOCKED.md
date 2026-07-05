# N4->N5->N6 Chained Shadow Smoke Execute Post-Check

Result: `BLOCKED`

Gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_EXECUTE_USER_CONFIRMATION_GATE_POSTCHECK`  
Layer role: `runtime_control`  
Generated on: `2026-06-10`

## Blocker

The authorized staged command exited with code `0`, and both N5 and N6 reports parsed. The post-check cannot be registered as `EXECUTE_PASS` because N6 wrote queued-only notification rows:

```text
expected user_notification_queue=0
actual user_notification_queue=50
```

The final gate planned `notification_queue_policy=deferred`, but the N6 execute runner used the immediate/default notification queue policy. This is a contract-vs-runner alignment issue, not an outbox consumption issue.

## N5 Execute Proof

N5 matched the final gate plan:

```text
common_action_run=1
common_action_quality_item=0
stock_action_fact=0
index_action_fact=0
board_action_fact=50
common_action_event=50
N5 common_event_outbox=50
common_event_inbox=50
common_event_consumer_checkpoint=50
common_position_state/event=0/0
```

Semantic distribution:

```text
ActionBlocked=50
ActionExecuted=0
ActionEligible=0
ActionSkipped=0
```

## N6 Execute Proof

Actual live rows:

```text
user_projection_run=1
user_signal_projection=50
user_signal_card=50
user_notification_queue=50
user_signal_decision=0
```

Projection distribution:

```text
ActionBlocked=50
ActionExecuted=0
```

## Source Preservation

N4 source outbox remains unchanged:

```text
TriggerMatched pending=556
delivered/delivering=0/0
```

Scoped N5 outbox remains pending:

```text
pending=50
delivered/delivering=0/0
N5 outbox status updated by N6=false
N5 outbox consumed by N6=false
N5 inbox/checkpoint refs for N6 source=0/0
```

## Downstream Forbidden Proof

No delivery/push/voice/mobile refs were found. Sim/order/trade/position refs are `0` or the optional tables are absent. `common_position_state/common_position_event=0/0`; `user_signal_decision=0`.

## Rollback Proof

Rollback SQL exists and was not executed:

```text
sql/N4_N5_N6_chained_shadow_smoke_20260608_probe_rollback.sql
```

It hard-fails before the first `DELETE` or `UPDATE`, has no `CASCADE`, `DROP`, or `TRUNCATE`, and covers `user_notification_queue`. A separate rollback final gate is required before any cleanup.

## Decision

`BLOCKED`

Do not enter post-review. The next gate should align the N6 notification queue policy and decide whether to preserve the queued-only rows as acceptable shadow evidence or rollback and rerun under deferred policy.

Recommended next gate:

```text
N4_N5_N6_CHAINED_SHADOW_SMOKE_NOTIFICATION_QUEUE_POLICY_ALIGNMENT_GATE
```
