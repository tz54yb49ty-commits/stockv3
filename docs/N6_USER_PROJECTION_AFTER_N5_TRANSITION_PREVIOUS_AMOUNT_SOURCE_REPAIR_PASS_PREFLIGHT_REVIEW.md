# N6 User Projection Preflight Review

Result: `PREFLIGHT_PASS`

Gate: `N6_USER_PROJECTION_AFTER_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_PREFLIGHT`

Mode: read-only preflight. No N6 execute, no N5 outbox consumption, no N1-N5 mutation, no worker, no voice/mobile/sim/position/order/real trade.

## Source Proof

- N5 post-review artifact result: `PASS`
- N5 execute report result: `EXECUTED`
- Source action run: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- Expected/read event count: `491`

## Candidate Input Proof

N6 preflight candidate input is scoped to `common_event_outbox` with:

- `source_layer=N5_action`
- `source_run_id=<source_action_run_id>`
- `status=pending`

Observed canonical N5 events:

| event_type | pending |
|---|---:|
| ActionBlocked | 469 |
| ActionExecuted | 22 |
| Total | 491 |

N5 outbox remains pending/unconsumed. Delivered/delivering count is `0`.

## N6 Baseline

Scoped by this `source_action_run_id`:

| table | rows |
|---|---:|
| user_projection_run | 0 |
| user_signal_projection | 0 |
| user_signal_card | 0 |
| user_notification_queue | 0 |

## N4 Boundary

N4 pending rows exist for context (`TriggerMatched=491`, `TriggerPendingMarketData=3835`), but the N6 preflight input does not read or reinterpret them. The N6 planner fetches projection events only from pending `N5_action` outbox rows for the source action run.

N6 does not infer trigger period from `condition_key`, `original_condition_key`, `required_periods`, or pending trace fields. Display/action mark uses N5 canonical payload fact `action_mark` only.

## Action Mark And Signal Proof

| action_mark | count |
|---|---:|
| 30m_shrink | 6 |
| 30m_volume | 11 |
| normal | 5 |
| null | 469 |

Runtime `signal_type` distribution:

| signal_type | count |
|---|---:|
| B_BUY | 157 |
| S_SELL | 334 |

`BUY_HINT` and `SELL_HINT` appear only as trace condition keys (`BUY_HINT=7`, `SELL_HINT=22`), not as runtime `signal_type`.

## Identity Checks

- `stock:SZ:301611 BUY:M,W,D`: allowed only through one N5 `ActionBlocked` action fact.
- `stock:SZ:300684 BUY:M,D`: no N5 row; remains a non-entry. It only appears in N4 pending context.
- `stock:SZ:300687 BUY:Y,M,D`: no N5 row; remains a non-entry. It only appears in N4 pending context.

## User Message Filter

Explicit user message filter:

- `ActionEligible`
- `ActionExecuted`

Source events: `491`

Eligible user messages: `22` (`ActionExecuted=22`)

Diagnosis-only events: `469` (`ActionBlocked=469`)

## Planner Result

Generated preflight artifact: `docs/N6_USER_PROJECTION_AFTER_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_PREFLIGHT.json`

Planner result: `DRY_RUN_PASS`

Current planner row counts:

| row type | planned |
|---|---:|
| user_projection_run | 1 |
| user_signal_projection | 22 |
| user_signal_card | 22 |
| user_notification_queue | 22 |
| n5_outbox_status_updates | 0 |
| user_signal_decision | 0 |
| user_sim_rows | 0 |

This gate did not execute N6 and did not write `user_notification_queue`. Future execute gate should explicitly freeze queue policy before execution.

## Forbidden Scope

- N6 projection executed: no
- N5 outbox consumed/updated: no
- N1-N5 facts updated: no
- N4 outbox status updated: no
- scheduler/worker started: no
- voice/mobile/sim/position/order/real trade touched: no
- old system read or modified: no

Recommended next gate: `N6_USER_PROJECTION_AFTER_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_CONTRACT_GATE`
