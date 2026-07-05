# N6 Action Projection 20260608 Until 09:52 Metric-Aware Retry Readiness

Result: `READINESS_PASS`

Layer role: `runtime_control`

This gate was read-only. It did not execute N6, write user projection/card/notification rows, consume or update N5 outbox/inbox/checkpoint rows, start a worker, run rollback SQL, trigger delivery/push/voice/mobile, write sim/position/PnL/real-trade rows, create proposal/order/trade rows, or touch the old system.

## Source Lineage

| item | value |
|---|---|
| N5 action run | `action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry` |
| N4 source run | `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry` |
| N3 metric run | `action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry` |
| planned N6 projection run | `user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry` |

## N5 Input Proof

| proof | value |
|---|---:|
| `common_action_run` | 1 |
| status | `passed` |
| P0/P1/P2 | `0/0/0` |
| read event count | 3920 |
| `stock_action_fact` | 113 |
| `index_action_fact` | 6 |
| `board_action_fact` | 0 |
| `common_action_event` | 119 |
| N5 outbox | 119 |
| metric trace in action facts | `119/119` |

N5 output is metric-aware and blocked-only:

| event | actual |
|---|---:|
| `ActionBlocked` | 119 |
| `ActionExecuted` | 0 |
| `ActionEligible` | 0 |
| `ActionSkipped` | 0 |

N5 outbox status:

```text
ActionBlocked / pending = 119
delivered / delivering = 0 / 0
downstream inbox / checkpoint refs = 0 / 0
```

Blocked reason:

```text
price_confirmation_failed = 119
```

## N6 Clean Baseline

Scoped N6/user rows for the metric-aware retry lineage are clean:

| table | rows |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |

Downstream refs are also zero for decision, notification/delivery, voice/mobile, sim/order/trade, position/PnL, and N6 virtual tables.

## Planned N6 Metric-Aware Retry Scope

Future N6 execute may project only the metric-aware N5 result:

| planned item | expected |
|---|---:|
| input events | 119 `ActionBlocked` |
| `user_projection_run` | 1 |
| `user_signal_projection` | 119 |
| `user_signal_card` | 119 |
| `user_notification_queue` | 0 |

Projection/card must preserve:

```text
action_state=blocked
event_type=ActionBlocked
blocked_reason=price_confirmation_failed
metric_run_id=action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
trigger_period=30m
primary_trigger_period=null
triggered_periods=[]
all_trigger_periods=[]
condition_key=BUY_HINT / SELL_HINT
```

`ActionExecuted=0` must not be shown as an executable recommendation. This remains readonly/shadow projection only; notification delivery, sim, order, trade, and position are forbidden.

## Boundary Proof

| boundary | proof |
|---|---:|
| N5 outbox remains pending | true |
| N5 outbox delivered/delivering | `0/0` |
| N5 inbox/checkpoint mutation | 0 |
| N4 `TriggerMatched / pending` | 119 |
| N4 `TriggerPendingMarketData / pending` | 3801 |
| N3 metric stock/index/board | `113/6/0` |

No N4/N3/N2/N1 facts were mutated in this gate.

## Rollback Requirement

Future N6 rollback must:

- hard-fail before any `DELETE` / `UPDATE`
- guard notification/delivery/sim/order/trade/position refs
- delete only scoped N6 metric-aware retry rows:
  `user_notification_queue`, `user_signal_card`, `user_signal_projection`, `user_projection_run`
- preserve N5 action facts and N5 outbox status
- preserve N4/N3/N2/N1 facts
- contain no `CASCADE`, `DROP`, or `TRUNCATE`

## Forbidden Scope Proof

```json
{
  "n6_execute_performed": false,
  "database_write": false,
  "user_projection_written": false,
  "user_signal_card_written": false,
  "user_notification_queue_written": false,
  "n5_outbox_consumed_or_updated": false,
  "n6_inbox_checkpoint_written": false,
  "worker_started": false,
  "delivery_push_voice_mobile": false,
  "sim_position_pnl_real_trade": false,
  "proposal_order_trade": false,
  "rollback_sql_executed": false,
  "old_system_touched": false
}
```

## Validation

- source JSON parse: `PASS`
- live N5 input proof: `PASS`
- N6 clean baseline proof: `PASS`
- downstream refs scan: `PASS`
- rollback requirement proof: `PASS`
- `git diff --check`: `PASS`

## Next Gate

Allowed:

`N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_CONTRACT_GATE`
