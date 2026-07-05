# N4->N5->N6 Chained Shadow Smoke Dry-Run

Result: `DRY_RUN_PASS`

Gate: `N4_N5_N6_CHAINED_SHADOW_SMOKE_DRY_RUN`  
Layer role: `runtime_control`  
Generated on: `2026-06-10`

## Dry-Run Scope

This dry-run plans a bounded staged shadow chain:

1. Read existing N4 `TriggerMatched` source rows without updating N4 outbox status.
2. Execute a new scoped N5 semantic action smoke from that N4 source if later authorized.
3. Execute a new scoped N6 shadow projection from the new N5 outbox if later authorized.

The N4 leg is a read-only source seed in this contract. The proposed N4 run id is reserved for lineage and baseline proof, but this contract does not plan new N4 trigger writes.

## Target Identifiers

| Item | Value |
|---|---|
| N4 trigger run id | `n4_n5_n6_chained_shadow_smoke_20260608_trigger_probe` |
| N4 consumer | `n4_trigger_worker_v1_n4_n5_n6_chained_shadow_probe` |
| N5 action run id | `n4_n5_n6_chained_shadow_smoke_20260608_action_probe` |
| N5 consumer | `n5_action_worker_v1_n4_n5_n6_chained_shadow_probe` |
| N6 projection run id | `n4_n5_n6_chained_shadow_smoke_20260608_projection_probe` |
| Source trigger run id | `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` |
| Metric run id | `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` |
| Max events | 50 |

## Source Readiness

| Source | Pending | Delivered | Delivering |
|---|---:|---:|---:|
| N4 `TriggerMatched` | 556 | 0 | 0 |
| N5 larger-scope outbox | 200 | 0 | 0 |

N5 larger-scope distribution remains `ActionBlocked=199`, `ActionExecuted=1`; this is registered source evidence and is not modified by this dry-run.

## Dry-Run Summary

| Metric | Count |
|---|---:|
| Chain event count | 50 |
| Planned N4 new trigger rows | 0 |
| Planned N5 `ActionBlocked` | 50 |
| Planned N5 `ActionExecuted` | 0 |
| Planned N5 outbox pending | 50 |
| Planned N6 projection rows | 50 |
| Planned notification queue rows | 0 |

Metric binding uses the deterministic metric run `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`. Opaque payload `action_confirmation` remains untrusted.

## Planned Staged Write Scope

N4 leg:

| Table | Planned Rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |

N5 leg:

| Table | Planned Rows |
|---|---:|
| `common_action_run` | 1 |
| `common_action_quality_item` | 0 |
| `stock_action_fact` | 0 |
| `index_action_fact` | 0 |
| `board_action_fact` | 50 |
| `common_action_event` | 50 |
| `common_event_outbox` | 50 |
| `common_event_inbox` | 50 |
| `common_event_consumer_checkpoint` | 50 |
| `common_position_state` | 0 |
| `common_position_event` | 0 |

N6 leg:

| Table | Planned Rows |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 50 |
| `user_signal_card` | 50 |
| `user_notification_queue` | 0 |
| `user_signal_decision` | 0 |

Forbidden writes remain zero: N4/N5 outbox status updates, N5 outbox consumption, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, and trade.

## Decision

`DRY_RUN_PASS`
