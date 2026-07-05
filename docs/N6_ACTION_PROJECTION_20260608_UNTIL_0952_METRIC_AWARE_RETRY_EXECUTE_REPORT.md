# N6 Action Projection 20260608 Until 09:52 Metric-Aware Retry Execute Report

Status: `EXECUTE_PASS`

Layer role: `N6_user`

Projection run:

```text
user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry
```

Source N5 action run:

```text
action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry
```

## Execute Proof

- runner result: `EXECUTED`
- preflight_result: `PREFLIGHT_PASS`
- notification_queue_policy: `deferred`
- quality P0/P1/P2: `0/5/2`
- worker_started: `false`
- committed: `true`

JSON report:

```text
docs/N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_EXECUTE_REPORT.json
```

## Row Count Proof

Live DB post-check:

| table | actual rows |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 119 |
| `user_signal_card` | 119 |
| `user_notification_queue` | 0 |

`user_projection_run.status` is `passed`.

## Metric-Aware Projection/Card Proof

Projection rows:

| proof | count |
|---|---:|
| `source_action_event_type=ActionBlocked` | 119 |
| `source_action_event_type=ActionExecuted` | 0 |
| `action_state=blocked` | 119 |
| `blocked_reason=price_confirmation_failed` | 119 |
| metric run preserved via `trace_json.source_projection_run_id` | 119 |
| metric run preserved via `trace_json.action_confirmation_metric.projection_run_id` | 119 |
| `trigger_period=30m` | 119 |
| `primary_trigger_period=null` | 119 |
| `triggered_periods=[]` | 119 |
| `all_trigger_periods=[]` | 119 |
| `condition_key=BUY_HINT` | 116 |
| `condition_key=SELL_HINT` | 3 |
| `action_mark is null` | 119 |

Card rows:

| proof | count |
|---|---:|
| `source_action_event_type=ActionBlocked` | 119 |
| `action_state=blocked` | 119 |
| `blocked_reason=price_confirmation_failed` | 119 |
| metric run preserved | 119 |
| `condition_key=BUY_HINT` | 116 |
| `condition_key=SELL_HINT` | 3 |

ActionExecuted rows were not projected as executable recommendations. No sim/order/trade/position intent was created.

## N5 Outbox Unchanged Proof

| proof | value |
|---|---:|
| `ActionBlocked pending` | 119 |
| delivered/delivering | `0/0` |
| common_event_inbox refs for source run | 0 |
| checkpoint rows for `N5_action` source layer | 0 |

N5 outbox was not consumed and no N5 outbox status was updated.

## Forbidden Scope Proof

| proof | value |
|---|---:|
| target `user_notification_queue` | 0 |
| common_event_delivery_attempt rows | 0 |
| user voice delivery table exists | `false` |
| user mobile delivery table exists | `false` |
| user notification delivery table exists | `false` |
| `user_signal_decision` refs | 0 |
| `user_sim_order` refs | 0 |
| `user_sim_trade` refs | 0 |
| `user_sim_position` refs | 0 |
| `n6_virtual_order` rows | 0 |
| `n6_virtual_trade` rows | 0 |
| `n6_virtual_position` rows | 0 |
| `n6_virtual_pnl_snapshot` rows | 0 |
| `common_position_state` rows | 0 |
| `common_position_event` rows | 0 |

No delivery/push/voice/mobile, worker, sim/position/pnl/real trade, proposal/order/trade, old-system touch, or N4/N3/N2/N1 mutation occurred.

## Rollback Proof

Rollback SQL:

```text
sql/N6_projection_20260608_until_0952_metric_aware_retry_rollback.sql
```

Static proof:

- hard-fail guards are before the first `DELETE`
- deletes only scoped N6 metric-aware retry rows
- preserves N5/N4/N3/N2/N1 facts
- no `CASCADE`
- no `DROP`
- no `TRUNCATE`
- rollback SQL was not executed in this gate

## Validation

- execute report JSON parse: `PASS`
- live row count proof: `PASS`
- metric-aware projection/card proof: `PASS`
- N5 outbox unchanged proof: `PASS`
- rollback static check: `PASS`
- git diff check: `PASS`

## Next Gate

Allowed to enter:

```text
N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_POST_REVIEW_GATE
```
