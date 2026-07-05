# N6 Action Projection 20260608 V13 Index-All Until 09:52 V4 Repair Retry Rollback Report

Status: `ROLLBACK_PASS`

Layer role: `N6_user`

Executed at: `2026-06-09T00:36:10+08:00`

## Scope

Target projection run:

```text
user_projection_shadow_20260608_v13_index_all_until_0952_v4_repair_retry__action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry
```

Rollback SQL:

```text
sql/N6_projection_20260608_v13_index_all_until_0952_v4_repair_retry_rollback.sql
```

This rollback only deletes scoped N6 shadow projection rows. It does not rollback or mutate N5, N4, N3, N2, or N1 facts/outbox.

## Deleted Rows

| table | deleted_rows |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 119 |
| `user_signal_card` | 119 |
| `user_notification_queue` | 0 |

SQL completed with exit code `0` and notice:

```text
notification_rows=0, card_rows=119, projection_rows=119, run_rows=1
```

## Post-Check Proof

Target scoped rows after rollback:

| table | rows |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |

Downstream refs:

| ref | rows |
|---|---:|
| `user_signal_decision` | 0 |
| `user_sim_order` | 0 |
| `user_sim_trade` | 0 |
| `user_sim_position` | 0 |
| `n6_virtual_order` | 0 |
| `n6_virtual_trade` | 0 |
| `n6_virtual_position` | 0 |
| `n6_virtual_pnl_snapshot` | 0 |

## Upstream Unchanged Proof

N5 upstream remained unchanged:

| proof | value |
|---|---:|
| `common_action_run` | `1/passed` |
| `common_action_event` | 119 |
| `stock_action_fact` | 113 |
| `index_action_fact` | 6 |
| `board_action_fact` | 0 |
| `ActionEligible pending` | 119 |
| `delivered/delivering` | `0/0` |
| `common_event_inbox refs for source run` | 0 |
| `common_event_consumer_checkpoint rows for N5_action` | 0 |

N4 upstream remained unchanged:

| proof | value |
|---|---:|
| `common_trigger_match` | 119 |
| `common_trigger_state` | 3920 |
| `TriggerMatched pending` | 119 |
| `TriggerPendingMarketData pending` | 3801 |

N3 metric proof:

| proof | value |
|---|---:|
| metric run | `1/passed` |
| metric rows | 119 |

## Rollback Static Proof

- Hard-fail guards execute before the first `DELETE`.
- Delete order is `user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run`.
- Optional voice/mobile/position tables are guarded with `to_regclass`.
- No `DROP`, `TRUNCATE`, or `CASCADE`.
- No N5/N4/N3/N2/N1 mutation.

## Forbidden Scope Proof

- N5 rollback executed: `false`
- N4 rollback executed: `false`
- N3 rollback executed: `false`
- N5 outbox consumed or updated: `false`
- N5 inbox/checkpoint written: `false`
- Worker started: `false`
- Delivery/push/voice/mobile: `false`
- Sim/position/pnl/real trade: `false`
- Proposal/order/trade: `false`
- Old system touched: `false`

## Next Gate

Allowed to enter:

```text
N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_ROLLBACK_POST_REVIEW_GATE_FOR_METRIC_AWARE_RERUN
```
