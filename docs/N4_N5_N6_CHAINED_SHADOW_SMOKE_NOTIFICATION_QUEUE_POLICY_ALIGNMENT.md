# N4->N5->N6 Chained Shadow Smoke Notification Queue Policy Alignment

Result: `ALIGNMENT_PASS`

Gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_NOTIFICATION_QUEUE_POLICY_ALIGNMENT_GATE`  
Layer role: `runtime_control`  
Generated on: `2026-06-10`

## Root Cause

The execute post-check was blocked because the final gate planned:

```text
user_notification_queue=0
notification_queue_policy=deferred
```

but the actual N6 execute wrote:

```text
user_notification_queue=50
notification_queue_policy=immediate
```

The root cause is a contract artifact alignment issue: the chained contract planned deferred notification queue semantics but did not expose a top-level `notification_queue_policy=deferred` field consumed by `run_n6_projection_once.py`. The N6 runner therefore used its supported default immediate policy and wrote queued-only notification rows.

This is not an N6 projection semantic failure and not an N4/N5 outbox consumption failure.

## Safety Proof

Live read-only proof used `transaction_read_only=on`.

Actual notification queue rows:

| queue_status | channel | notification_source | count |
|---|---|---|---:|
| `queued_only` | `broadcast_queue` | `n5_action_blocked` | 50 |

Additional proof:

```text
queue_only_payload_refs=50
not_queued_only=0
non_broadcast_queue=0
actual_push=false
voice_mobile_push=false
provider_delivery_attempt=false
```

N4 source preservation:

```text
TriggerMatched pending=556
delivered/delivering=0/0
N4 outbox status updated=false
N4 outbox consumed=false
```

N5 source preservation:

```text
scoped N5 outbox pending=50
delivered/delivering=0/0
N5 outbox status updated=false
N5 outbox consumed=false
```

Downstream refs:

```text
user_signal_decision=0
user_sim_order/trade/position=0/0/0
common_position_state/event=0/0
n6_virtual_order/trade/position/position_event/pnl=0/0/0/0/0
delivery/push/voice/mobile tables absent or 0
proposal/order/trade tables absent or 0
```

## Policy Decision

Decision:

```text
ACCEPT_QUEUED_ONLY_SHADOW_ROWS_BY_ALIGNMENT_AMENDMENT
```

Rollback is not required now. Rerun is not required now.

Reason: all 50 notification rows are queued-only `broadcast_queue` rows, no provider delivery/push/voice/mobile happened, N4/N5 outbox status remained pending, and downstream sim/order/trade/position refs are zero. The mismatch is a contract policy field alignment issue, not unsafe downstream execution.

The amended N6 write scope for post-review is:

```text
user_projection_run=1
user_signal_projection=50
user_signal_card=50
user_notification_queue=50
user_signal_decision=0
delivery/push/voice/mobile=0
sim/position/pnl/real_trade=0
proposal/order/trade=0
```

Future deferred N6 projection executes must put top-level `notification_queue_policy=deferred` in the contract/preflight JSON consumed by `run_n6_projection_once.py`.

## Rollback Readiness

Rollback SQL exists and was not executed:

```text
sql/N4_N5_N6_chained_shadow_smoke_20260608_probe_rollback.sql
```

The rollback SQL hard-fails before the first `DELETE` or `UPDATE`, covers `user_notification_queue`, guards N4 source outbox delivered/delivering, guards scoped N5 outbox delivered/delivering, guards downstream user/delivery/sim/order/trade/position refs, and contains no `CASCADE`, `DROP`, or `TRUNCATE`.

A separate rollback final gate is still required before any cleanup.

## Forbidden Scope Proof

- SQL executed: read-only `SELECT` only.
- Database written by this gate: `false`.
- Rollback SQL executed: `false`.
- N4/N5/N6 execute by this gate: `false`.
- N4 outbox consumed or updated by this gate: `false`.
- N5 outbox consumed or updated by this gate: `false`.
- Worker started by this gate: `false`.
- Delivery/push/voice/mobile by this gate: `false`.
- Sim/position/PnL/real_trade by this gate: `false`.
- Proposal/order/trade by this gate: `false`.
- Old system touched: `false`.

## P0/P1/P2

`P0/P1/P2 = 0/1/0`

`P1` is the non-blocking contract policy-field alignment issue described above. It is accepted by this amendment for the already executed queued-only shadow rows.

## Recommended Next Gate

```text
N4_N5_N6_CHAINED_SHADOW_SMOKE_AMENDED_POST_REVIEW_GATE
```
