# N4 Worker Bounded Smoke 20260608 Trigger Semantic Probe Preflight

Result: `PREFLIGHT_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`

Generated at: `2026-06-10T09:30:30+08:00`

## Decision

Preflight passes for execute user confirmation.

## Baseline Proof

Target semantic smoke rows are all zero:

| table | rows |
|---|---:|
| `common_trigger_run` | 0 |
| `common_trigger_quality_item` | 0 |
| `common_trigger_state` | 0 |
| `common_trigger_match` | 0 |
| `common_event_outbox` | 0 |
| `common_event_inbox` | 0 |
| `common_event_consumer_checkpoint` | 0 |

## Source Proof

| proof | value |
|---|---:|
| selected source events | 10 |
| semantic evaluations | 10 |
| source/oracle intersection | 10 |
| selected source pending | 10 |
| selected source locked rows | 0 |
| selected source delivered/delivering | 0 |
| stop file exists | false |

## Planned Write Scope

| table | rows |
|---|---:|
| `common_trigger_run` | 1 |
| `common_trigger_quality_item` | 2 |
| `common_event_inbox` | 10 |
| `common_event_consumer_checkpoint` | 10 |
| `common_trigger_state` | 10 |
| `common_trigger_match` | 10 |
| `common_event_outbox` | 10 |

## Semantic Proof

- `TriggerMatched=10`
- `TriggerPendingMarketData=0`
- `TriggerStateChanged=0`
- `fixture_only=true`
- `source_oracle_run_id` preserved
- `not_new_market_decision=true`
- N5 entry only for `TriggerMatched`
- oracle remains read-only

## Boundary Proof

- N3 outbox update forbidden and planned as false
- N5/N6 forbidden and planned as false
- delivery/push/voice/mobile forbidden and planned as false
- sim/position/order/trade/real_trade forbidden and planned as false

## Rollback Proof

Rollback SQL exists and is scoped:

`sql/N4_worker_bounded_smoke_20260608_trigger_semantic_probe_rollback.sql`

It hard-fails before row removal and preserves N3 facts/outbox plus the oracle lineage.

