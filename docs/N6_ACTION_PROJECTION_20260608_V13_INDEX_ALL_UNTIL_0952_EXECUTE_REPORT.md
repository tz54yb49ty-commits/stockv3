# N6 Action Projection 20260608 v13 Index-All Until 09:52 Execute Report

Status: `EXECUTE_PASS`

Layer role: `N6_user`

Date: 2026-06-08

Projection run:

```text
user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952
```

Source N5 action run:

```text
action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
```

This execute wrote only N6 readonly shadow projection/card rows. It did not write `user_notification_queue`, consume or update N5 outbox, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/proposal/order/trade/real-trade scope.

## Execute Command

The confirmed command completed with exit code 0 and wrote the JSON report to:

```text
docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json
```

JSON report result:

```text
EXECUTED
```

## Actual Row Counts

| table | expected | actual |
|---|---:|---:|
| `user_projection_run` | 1 | 1 |
| `user_signal_projection` | 201 | 201 |
| `user_signal_card` | 201 | 201 |
| `user_notification_queue` | 0 | 0 |

Projection distribution:

| source_action_event_type | action_state | count |
|---|---|---:|
| `ActionEligible` | `eligible` | 201 |

Card distribution:

| card_status | count |
|---|---:|
| `candidate` | 201 |

## N5 Outbox Unchanged Proof

N5 outbox for the source action run remains:

| event_type | status | count |
|---|---|---:|
| `ActionEligible` | `pending` | 201 |

No delivered or delivering rows were introduced by this execute.

## Notification Queue Proof

`user_notification_queue` scoped to this projection run:

```text
0
```

The execute report notification plan confirms:

```text
planned_notification_count=0
deferred=true
actual_push=false
voice_mobile_push=false
provider_delivery_attempt=false
```

## Forbidden Scope Proof

Scoped linked downstream rows remain 0:

| table | count |
|---|---:|
| `user_signal_decision` | 0 |
| `user_sim_order` | 0 |
| `user_sim_trade` | 0 |
| `user_sim_position` | 0 |
| `n6_virtual_order` | 0 |
| `n6_virtual_trade` | 0 |
| `n6_virtual_position` | 0 |
| `n6_virtual_pnl_snapshot` | 0 |

No N5 inbox/checkpoint writes were requested or performed. No worker, delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, or real-trade path was executed.

N5 inbox/checkpoint proof:

- `common_event_inbox` rows for this `source_action_run_id`: 0.
- Runner static scan found no `common_event_inbox` write path and no `common_event_consumer_checkpoint` update path in `scripts/run_n6_projection_once.py` or `src/ashare_v3/user/projection_execute.py`.

## Rollback Proof

Rollback SQL:

```text
sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql
```

Static rollback check:

- `RAISE EXCEPTION` hard-fail appears before the first executable `DELETE`.
- Delete scope is limited to this `user_projection_run_id`.
- Delete order is `user_notification_queue` -> `user_signal_card` -> `user_signal_projection` -> `user_projection_run`.
- No `CASCADE`.
- No `TRUNCATE`.
- No `DELETE FROM common_event_outbox`.
- No N1-N5 facts or outbox mutation.

Rollback was not executed.

## Warnings

The execute report retained known display-field warnings:

- `board_context_missing`
- `current_price_missing`
- `display_basis_missing`
- `expected_return_pct_missing`
- `target_price_missing`

These are presentation context warnings and did not expand write scope.

## Decision

`EXECUTE_PASS`

Allowed next gate:

```text
N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_POST_REVIEW_GATE
```
