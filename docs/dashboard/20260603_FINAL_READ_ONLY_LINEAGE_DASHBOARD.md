# 20260603 Final Read-Only Lineage Dashboard

Result: `DASHBOARD_ARTIFACT_PASS`

Layer role: `runtime_control`<br>
Generated at: `2026-06-04T17:22:49+0800`<br>
Trade date: `20260603`

## Endpoint

Current endpoint: `N6 shadow projection / queued_only preserved`.

This dashboard is read-only evidence. It does not mean real delivery, push, voice,
mobile, sim, position, or real trade happened. The N6 cards are blocked shadow
cards only; they must not be displayed as buy/sell recommendations or executable
actions.

## N1 to N6 Baseline

| Layer | Run / scope | Status | Key rows |
|---|---|---|---|
| N1 | `common_trade_calendar(20260603)` and 20260602 source baseline | ready | `is_open=true`, prev/next=`20260602/20260604` |
| N2 | `condition_layer_20260602_source_20260602_v1` | `passed_active`, P0/P1/P2=`0/9/3` | source/for trade date=`20260602/20260603` |
| N3 | subscription / A1 / B1 | passed | B1 stock/index/board/total=`1963/83/428/2474`, fact-only |
| N4 v4 | `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` | passed, P0/P1/P2=`0/0/0` | state/match/outbox=`863/863/863` |
| N5 v1 | `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` | passed, P0/P1/P2=`0/0/0` | ActionBlocked=`863` |
| N6 shadow | `user_projection_shadow_20260603_v1__action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` | passed, P0/P1/P2=`0/5/2` | projection/card/source_queue/preview=`863/863/863/0` |

## Pending Outbox

| Source | Event | Status | Rows |
|---|---|---|---:|
| N4 v4 | `TriggerMatched` | `pending` | 863 |
| N5 v1 | `ActionBlocked` | `pending` | 863 |

N5 outbox consumed/updated: `false`.<br>
N6 inbox/checkpoint refs for N5 action: `0/0`.

## N5 Blocked Reason

| blocked_reason | Rows |
|---|---:|
| `price_confirmation_failed` | 838 |
| `amount_confirmation_failed` | 25 |
| `metric_missing` | 0 |

## N6 Dashboard Readiness

- Source queue preserved: `n5_action_blocked / queued_only / broadcast_queue = 863`.
- Delivery noop preview rollback passed: target preview rows=`0`.
- Allowed display mode: shadow blocked card / queued-only dashboard.
- Forbidden display mode: buy/sell recommendation, executable action, real delivery state.

## Forbidden Scope Proof

| Guard | Rows / status |
|---|---:|
| `common_event_delivery_attempt` | 0 |
| `user_signal_decision` | 0 |
| `common_position_state/common_position_event` | 0/0 |
| `user_sim_order/user_sim_trade/user_sim_position` | 0/0/0 |
| worker / real delivery / push / voice / mobile / sim / position / real trade | false |

## Rollback Dependency Order

If rollback is explicitly requested, go downstream to upstream:

1. N6 shadow projection
2. N5 v1 market-action-confirmation action
3. N4 v4 trigger
4. N4 trigger context snapshot
5. N3 B1 snapshot
6. N3 A1 previous-day minute preload
7. N3 subscription
8. N2 condition
9. N1 source/calendar

N6 delivery preview rows are already rolled back and do not need a separate
preview rollback step.

## Remaining Gaps

- N4 outbox remains pending.
- N5 outbox remains pending.
- N6 is shadow / queued_only only, not real delivery.
- Real delivery, push, voice, mobile, sim, position, or real trade requires a
  separate readiness/final gate.

## Next Allowed Gates

- `runtime_control` read-only dashboard / lineage review.
- N6 rollback review, only if rollback is explicitly requested.
- Separate real delivery/push readiness gate, only if explicitly requested.
