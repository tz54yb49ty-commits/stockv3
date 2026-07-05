# N6 Full Metric-Union Historical Projection Repair Contract

Status: `CONTRACT_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This gate defines a metadata-only N6 projection/card repair contract for the 20260605 action projection. It does not execute the repair, does not write the database, does not consume or update any outbox, and does not create notifications, proposals, orders, trades, positions, PnL, delivery, push, voice, mobile, sim, or real trade side effects.

## Source Scope

- Source action run: `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- Source trigger run: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N6 projection run: `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- N5 repair policy: `n5.full_metric_union_historical_metadata_repair.v1`
- N6 repair run: `n6_full_metric_union_historical_projection_repair_20260605_v1`
- N6 repair policy: `n6.full_metric_union_historical_projection_repair.v1`

## Current N6 Metadata

The current N6 projection/card metadata still reflects the pre-repair N5 state:

| blocked_reason | Current N6 rows |
|---|---:|
| `price_confirmation_failed` | 305 |
| `metric_missing` | 289 |
| `amount_confirmation_failed` | 10 |

Action counts remain:

| event type | count |
|---|---:|
| `ActionExecuted` | 1 |
| `ActionBlocked` | 604 |

## Target Metadata

The target N6 metadata mirrors the N5 full metric-union historical repair:

| blocked_reason | Target N6 rows |
|---|---:|
| `price_confirmation_failed` | 587 |
| `metric_missing` | 0 |
| `amount_confirmation_failed` | 17 |

Action counts must remain unchanged:

| event type | count |
|---|---:|
| `ActionExecuted` | 1 |
| `ActionBlocked` | 604 |

## Diff Scope

Planned metadata changes:

| transition | projection rows | card rows |
|---|---:|---:|
| `metric_missing -> price_confirmation_failed` | 282 | 282 |
| `metric_missing -> amount_confirmation_failed` | 7 | 7 |
| total affected | 289 | 289 |

Sample proof:

- `stock:SH:688690`
- projection/card: `5954 / 5954`
- source event: `evt_51a3ea62bfb8e93407a5859107a95c0e14ad6d70`
- old N6 blocked_reason: `metric_missing`
- target blocked_reason: `amount_confirmation_failed`
- target metric coverage: `full`

## Allowed Update Scope

Future execute may update only metadata fields in existing rows:

- `user_signal_projection.source_payload_json.payload_json.blocked_reason`
- `user_signal_projection.trace_json.blocked_reason`
- `user_signal_projection.trace_json.metric_union_*`
- `user_signal_projection.trace_json.repair_trace`
- `user_signal_card.card_payload_json.blocked_reason`
- `user_signal_card.trace_json.blocked_reason`
- `user_signal_card.trace_json.metric_union_*`
- `user_signal_card.trace_json.repair_trace`

## Forbidden Update Scope

Future execute must not update:

- `user_signal_projection.projection_status`
- `user_signal_card.card_status`
- `source_action_event_type`
- `action_state`
- `ActionExecuted` count or semantics
- `ActionBlocked` count or semantics
- `user_notification_queue`
- N5 outbox status
- N5/N4/N3/N2/N1 facts
- proposal/order/trade/position/PnL/sim/delivery/push/voice/mobile/real trade rows

## Payload

Dry-run payload path:

```text
docs/N6_full_metric_union_historical_projection_repair_payload.json
```

The payload contains the 289 row-level metadata transitions and the previous metadata needed for rollback.

## Rollback Contract

Rollback SQL:

```text
sql/N6_full_metric_union_historical_projection_repair_20260605_rollback.sql
```

Rollback is metadata-only:

- restores previous blocked_reason metadata
- removes N6 metric-union repair metadata
- removes repair trace metadata
- does not delete projection/card rows
- does not delete or update N5/N4/N3 data
- hard-fails before the first `UPDATE` if downstream refs exist

## Gate Decision

`CONTRACT_PASS`

This contract may proceed to `N6_FULL_METRIC_UNION_HISTORICAL_PROJECTION_REPAIR_EXECUTE_FINAL_GATE_REVIEW`.
