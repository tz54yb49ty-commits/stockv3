# N4 Worker Bounded Smoke 20260608 Trigger Semantic Probe Dry Run

Result: `DRY_RUN_PASS`

Gate: `N4_WORKER_BOUNDED_SMOKE_TRIGGER_SEMANTIC_CONTRACT_GATE`

Generated at: `2026-06-10T09:30:30+08:00`

## Summary

Semantic oracle source selection is now aligned. The runner loads oracle evaluations first, selects the N3 `MarketSnapshotUpdated` events referenced by those evaluations, and then builds transition plans.

This dry-run remains read-only:

- no smoke execute
- no DB write
- no N3 outbox update/consume
- no N5/N6
- no worker

## Scope

- `smoke_run_id=n4_worker_bounded_smoke_20260608_trigger_semantic_probe`
- `consumer_name=n4_trigger_worker_v1_bounded_smoke_semantic_probe`
- `semantic_smoke=true`
- `semantic_oracle_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- `max_events=10`
- `max_runtime_seconds=120`
- `heartbeat_interval_seconds=10`
- `status_json=docs/N4_WORKER_BOUNDED_SMOKE_20260608_TRIGGER_SEMANTIC_PROBE_STATUS.json`
- `stop_file=tmp/n4_worker_bounded_smoke_20260608_trigger_semantic_probe.stop`

## Prerequisite Proof

- source selection alignment: `ALIGNMENT_PASS`
- trigger semantic readiness: `READINESS_PASS`
- semantic runner alignment: `ALIGNMENT_PASS`
- scoped smoke post-review: `POST_REVIEW_PASS`
- expanded smoke post-review: `POST_REVIEW_PASS`
- target semantic baseline rows: `0/0/0/0/0/0/0`
- stop file exists: `false`

## Oracle / Source Proof

Read-only oracle:

`trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`

| proof | value |
|---|---:|
| oracle run exists/status | 1 / passed |
| oracle `TriggerMatched` | 556 |
| selected source events | 10 |
| semantic evaluations | 10 |
| source/oracle intersection | 10 |
| selected source status | pending |
| selected source layer | N3_market_data |
| selected source event type | MarketSnapshotUpdated |
| selected source locked rows | 0 |
| selected source delivered/delivering | 0 |

Semantic trace proof:

- `fixture_only=true`
- `source_oracle_run_id=trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- `not_new_market_decision=true`
- `n5_entry_allowed=true` for `TriggerMatched`
- oracle facts/outbox are read-only

## Dry-Run Result

| item | value |
|---|---:|
| accepted source events | 10 |
| skipped duplicate source events | 0 |
| transition event plans | 10 |
| `TriggerMatched` | 10 |
| `TriggerPendingMarketData` | 0 |
| `TriggerStateChanged` | 0 |

## Planned Write Scope

If future execute is authorized:

| table | rows |
|---|---:|
| `common_trigger_run` | 1 |
| `common_trigger_quality_item` | 2 |
| `common_event_inbox` | 10 |
| `common_event_consumer_checkpoint` | 10 |
| `common_trigger_state` | 10 |
| `common_trigger_match` | 10 |
| `common_event_outbox` | 10 |

Forbidden writes remain false:

- N3 outbox status update = `false`
- N5/N6 = `false`
- delivery/push/voice/mobile = `false`
- sim/position/order/trade/real_trade = `false`

## P0/P1/P2

| severity | count |
|---|---:|
| P0 | 0 |
| P1 | 2 |
| P2 | 0 |

P1 notes:

- The oracle has downstream refs and must remain read-only.
- The oracle covers `TriggerMatched` only; pending/state-changed paths require a separate deterministic fixture or oracle.

## Boundary

This dry-run gate did not:

- execute smoke
- write DB
- update or consume N3 outbox
- enter N5/N6
- start a worker
- touch delivery/push/voice/mobile
- touch sim/position/pnl/real_trade
- touch proposal/order/trade
- touch the old system

