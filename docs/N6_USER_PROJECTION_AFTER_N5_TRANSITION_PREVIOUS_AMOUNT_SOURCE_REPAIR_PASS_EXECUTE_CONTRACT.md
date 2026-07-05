# N6 User Projection Execute Contract Retry

Result: `CONTRACT_PASS`

Gate: `N6_USER_PROJECTION_AFTER_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_CONTRACT_GATE_RETRY_AFTER_QUEUE_POLICY_ALIAS_ALIGNMENT`

This gate only freezes and verifies the execute contract. It does not authorize or execute N6 projection.

## Scope

- trade_date: `20260617`
- source_action_run_id: `action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- projection_run_id: `v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1`

## Contract Freeze

- `notification_queue_policy=deferred_no_queue_write`
- `expected_user_notification_queue_delta=0`
- voice/mobile/sim/position/order/real_trade policy: `deferred`
- user message filter: `ActionEligible`, `ActionExecuted`
- `ActionBlocked` and `ActionSkipped` are diagnosis-only for this ordinary user projection contract.

## Runner Alias Proof

Validation probe:

```text
deferred_no_queue_write + user_notification_queue=0 -> PASS
deferred_no_queue_write + user_notification_queue=1 -> notification_queue_deferred_contract_plans_queue_rows
unknown policy -> notification_queue_policy_not_allowed
```

In-memory execute write plan under `deferred_no_queue_write`:

| write target | count |
|---|---:|
| user_projection_run | 1 |
| user_signal_projection | 22 |
| user_signal_card | 22 |
| user_notification_queue | 0 |

Write tables:

```text
user_projection_run
user_signal_projection
user_signal_card
```

`user_notification_queue` is not in `write_tables`.

## N5 Input Proof

N5 source input is pending canonical N5 outbox only:

| event/status | count |
|---|---:|
| ActionBlocked/pending | 469 |
| ActionExecuted/pending | 22 |
| Total | 491 |
| delivered/delivering | 0 |

N4 pending rows exist only as context and are not N6 input:

| N4 event/status | count |
|---|---:|
| TriggerMatched/pending | 491 |
| TriggerPendingMarketData/pending | 3835 |

## Baseline Proof

Scoped rows before execute:

| table | rows |
|---|---:|
| user_projection_run | 0 |
| user_signal_projection | 0 |
| user_signal_card | 0 |
| user_notification_queue | 0 |

## Semantic Proof

N6 does not infer display or notification fields from N4 pending rows, `condition_key`, `original_condition_key`, `required_periods`, or pending trigger trace fields.

N5 canonical action marks:

| action_mark | count |
|---|---:|
| 30m_shrink | 6 |
| 30m_volume | 11 |
| normal | 5 |
| null | 469 |

Runtime signal types:

| signal_type | count |
|---|---:|
| B_BUY | 157 |
| S_SELL | 334 |

## Rollback

Rollback SQL:

`sql/N6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_rollback.sql`

Static proof:

- scoped by `projection_run_id` and `source_action_run_id`
- hard-fail before first `DELETE`
- no `CASCADE`
- no `DROP`
- no `TRUNCATE`

## Forbidden Scope

- N6 projection executed: no
- database written: no
- user_notification_queue written: no
- N5 outbox consumed/updated: no
- N4 outbox updated: no
- N1-N5 facts updated: no
- scheduler/worker started: no
- voice/mobile/sim/position/order/real trade touched: no
- old system read/modified: no

Next step requires a separate user confirmation gate.
